from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.services import create_notification
from orders.models import Order
from orders.realtime import broadcast_order_event
from restaurants.tenancy import resolve_restaurant

from .gateways import (
    build_callback_url,
    build_redirect_url,
    get_gateway,
)
from .models import Payment


def _restaurant(request):
    return resolve_restaurant(request)


def _order_payload_min(order: Order) -> dict:
    return {
        'id': order.id,
        'table_number': order.table.number if order.table_id else None,
        'title': (
            f'Masa {order.table.number}'
            if order.table_id
            else f'Al-apar #{order.id}'
        ),
        'status': order.status,
        'total_amount': str(order.total_amount),
    }


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            'id',
            'order',
            'amount',
            'currency',
            'method',
            'gateway',
            'status',
            'payment_url',
            'qr_code_url',
            'gateway_invoice_id',
            'gateway_transaction_id',
            'paid_at',
            'expires_at',
            'failure_reason',
            'created_at',
        )


class CreatePaymentView(APIView):
    """
    Müştəri "Hesabı öde" → server-side invoice.
    Frontend heç vaxt gateway-ə birbaşa getmir.
    """

    @transaction.atomic
    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        order_id = request.data.get('order_id')
        order = (
            Order.objects.select_related('table', 'restaurant')
            .filter(pk=order_id, restaurant=restaurant)
            .first()
        )
        if not order:
            return Response({'detail': 'Sifariş tapılmadı'}, status=404)

        # Artıq ödənilibsə — mövcud paid qaytar
        paid = order.payments.filter(status='paid').first()
        if paid:
            return Response(PaymentSerializer(paid).data)

        # Aktiv pending varsa yenidən istifadə et
        pending = (
            order.payments.filter(status__in=('pending', 'processing'))
            .order_by('-created_at')
            .first()
        )
        if pending and pending.payment_url:
            return Response(PaymentSerializer(pending).data)

        gateway_name = (
            request.data.get('gateway')
            or restaurant.payment_gateway
            or 'mock'
        )
        if getattr(settings, 'PAYMENTS_MOCK', True):
            gateway_name = 'mock'

        gateway = get_gateway(gateway_name)
        api_key = restaurant.payment_api_key or getattr(
            settings, 'PAYRIFF_SECRET_KEY', ''
        ) or getattr(settings, 'EPOINT_SECRET_KEY', '')

        amount = Decimal(order.total_amount)
        # Servis haqqı / ƏDV — hesab-faktura məntiqi sonra; indilik order total
        if restaurant.service_charge_enabled and restaurant.service_charge_percent:
            amount = amount * (
                1 + Decimal(restaurant.service_charge_percent) / Decimal(100)
            )
            amount = amount.quantize(Decimal('0.01'))

        minutes = getattr(settings, 'PAYMENT_EXPIRE_MINUTES', 15)
        expires_at = timezone.now() + timedelta(minutes=minutes)

        payment = Payment.objects.create(
            order=order,
            restaurant=restaurant,
            amount=amount,
            currency=restaurant.currency or 'AZN',
            method='online',
            gateway=gateway.name,
            status='pending',
            expires_at=expires_at,
        )

        description = (
            f'Masa {order.table.number} hesabı'
            if order.table_id
            else f'Sifariş #{order.id}'
        )
        try:
            result = gateway.create_invoice(
                amount=amount,
                currency=payment.currency,
                order_id=order.id,
                description=description,
                callback_url=build_callback_url(gateway.name),
                redirect_url=build_redirect_url(order.id),
                api_key=api_key,
            )
        except Exception as exc:
            payment.status = 'failed'
            payment.failure_reason = str(exc)[:255]
            payment.save(
                update_fields=['status', 'failure_reason', 'updated_at']
            )
            create_notification(
                restaurant=order.restaurant,
                type='payment_failed',
                message=(
                    f'Sifariş #{order.id} ödənişi uğursuz oldu: '
                    f'{str(exc)[:80]}'
                ),
                link='/history',
                related_order=order,
                related_table=order.table,
            )
            return Response(
                {'detail': 'Ödəniş sessiyası yaradılmadı', 'error': str(exc)},
                status=502,
            )

        payment.payment_url = result.payment_url or ''
        payment.qr_code_url = result.qr_code_url or ''
        payment.gateway_invoice_id = result.invoice_id or ''
        payment.raw_response = result.raw or {}
        payment.status = 'processing'
        payment.save()

        return Response(PaymentSerializer(payment).data, status=201)


class PaymentStatusView(APIView):
    """Redirect sonrası polling — həqiqət webhook-dadır."""

    def get(self, request, pk):
        payment = Payment.objects.filter(pk=pk).select_related('order').first()
        if not payment:
            return Response({'detail': 'Ödəniş tapılmadı'}, status=404)
        return Response(PaymentSerializer(payment).data)


class OrderPaymentStatusView(APIView):
    def get(self, request, order_id):
        restaurant = _restaurant(request)
        order = Order.objects.filter(
            pk=order_id, restaurant=restaurant
        ).first()
        if not order:
            return Response({'detail': 'Sifariş tapılmadı'}, status=404)
        payment = order.payments.order_by('-created_at').first()
        if not payment:
            return Response({'status': 'none', 'payment': None})
        return Response(
            {
                'status': payment.status,
                'payment': PaymentSerializer(payment).data,
            }
        )


def _apply_webhook_result(parsed: dict, raw: dict, gateway_name: str):
    order_id = parsed.get('order_id')
    order = Order.objects.select_related('restaurant', 'table').filter(
        pk=order_id
    ).first()
    if not order:
        return False, 'order_not_found'

    payment = (
        order.payments.filter(
            gateway=gateway_name,
            status__in=('pending', 'processing', 'failed'),
        )
        .order_by('-created_at')
        .first()
    )
    if not payment:
        payment = order.payments.order_by('-created_at').first()
    if not payment:
        return False, 'payment_not_found'

    tx = parsed.get('transaction_id') or ''
    if parsed.get('status') == 'success':
        try:
            with transaction.atomic():
                # Unikal transaction_id — təkrar webhook
                if tx:
                    exists = (
                        Payment.objects.filter(gateway_transaction_id=tx)
                        .exclude(pk=payment.pk)
                        .exists()
                    )
                    if exists:
                        return True, 'duplicate_tx'
                changed = payment.mark_paid(tx, raw=raw)
                if changed:
                    # Masa: hesab gözləmə / tamamlanma
                    order.status = 'completed'
                    if not order.completed_at:
                        order.completed_at = timezone.now()
                    order.save(
                        update_fields=['status', 'completed_at', 'updated_at']
                    )
                    if order.table_id:
                        table = order.table
                        table.awaiting_bill = False
                        table.needs_cleaning = True
                        table.save(
                            update_fields=['awaiting_bill', 'needs_cleaning']
                        )
                    from orders.kanban import serialize_kanban_card

                    broadcast_order_event(
                        order.restaurant.slug,
                        'order.completed',
                        serialize_kanban_card(
                            Order.objects.filter(pk=order.pk)
                            .select_related('table', 'served_by')
                            .prefetch_related('items__menu_item')
                            .first()
                        ),
                    )
                    broadcast_order_event(
                        order.restaurant.slug,
                        'payment.paid',
                        {
                            **_order_payload_min(order),
                            'payment_id': payment.id,
                            'amount': str(payment.amount),
                        },
                    )
        except IntegrityError:
            return True, 'duplicate_tx'
        return True, 'paid'

    payment.mark_failed(reason='gateway_failed', raw=raw)
    create_notification(
        restaurant=order.restaurant,
        type='payment_failed',
        message=f'Sifariş #{order.id} — gateway ödənişi uğursuz',
        link='/history',
        related_order=order,
        related_table=order.table,
    )
    return True, 'failed'


@csrf_exempt
def payment_webhook(request, gateway: str):
    """
    Yalnız webhook-a güvən. İmza yoxlanışı məcburidir (mock istisna).
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    body = request.body
    signature = (
        request.headers.get('X-Signature')
        or request.headers.get('X-Epoint-Signature')
        or request.META.get('HTTP_X_SIGNATURE')
    )
    gw = get_gateway(gateway)
    secret = ''
    if gateway == 'payriff':
        secret = getattr(settings, 'PAYRIFF_WEBHOOK_SECRET', '')
    elif gateway == 'epoint':
        secret = getattr(settings, 'EPOINT_WEBHOOK_SECRET', '')
    elif gateway == 'mock':
        secret = getattr(settings, 'PAYMENTS_MOCK_WEBHOOK_SECRET', '')

    if not gw.verify_webhook(body, signature, secret):
        return HttpResponse(status=403)

    import json

    try:
        data = json.loads(body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    parsed = gw.parse_webhook(data)
    ok, _code = _apply_webhook_result(parsed, data, gw.name)
    return HttpResponse(status=200 if ok else 404)


@csrf_exempt
def mock_pay_page(request, invoice_id: str):
    """
    Dev mock: brauzerdə açılan 'ödəniş' səhifəsi.
    Uğurlu ödəniş → birbaşa eyni webhook məntiqi.
    """
    payment = (
        Payment.objects.select_related('order', 'restaurant')
        .filter(gateway_invoice_id=invoice_id)
        .first()
    )
    if not payment:
        return HttpResponse('Ödəniş tapılmadı', status=404)

    if request.method == 'POST' or request.GET.get('confirm') == '1':
        raw = {
            'order_id': payment.order_id,
            'status': 'success',
            'transaction_id': f'tx-{invoice_id}',
            'invoice_id': invoice_id,
            'amount': str(payment.amount),
        }
        parsed = get_gateway('mock').parse_webhook(raw)
        _apply_webhook_result(parsed, raw, 'mock')
        return HttpResponseRedirect(build_redirect_url(payment.order_id))

    html = f"""
    <html><body style="font-family:sans-serif;padding:2rem">
      <h2>Mock ödəniş</h2>
      <p>Sifariş #{payment.order_id} — {payment.amount} {payment.currency}</p>
      <form method="post"><button type="submit">Ödə (simulyasiya)</button></form>
    </body></html>
    """
    return HttpResponse(html)


class ExpirePaymentsView(APIView):
    """Cron/Celery əvəzinə əl ilə və ya scheduler ilə çağrıla bilər."""

    def post(self, request):
        now = timezone.now()
        qs = Payment.objects.filter(
            status__in=('pending', 'processing'),
            expires_at__lt=now,
        )
        count = qs.update(status='expired')
        return Response({'expired': count})
