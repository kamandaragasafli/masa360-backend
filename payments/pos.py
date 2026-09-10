"""
POS / Kassa ödəniş — nağd və kart (ledger + sifariş tamamlanması).
"""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from menu.models import MenuItem
from orders.kanban import serialize_kanban_card
from orders.kot import (
    build_receipt_payload,
    enqueue_customer_receipt,
    enqueue_kitchen_tickets,
)
from orders.models import Order, OrderItem
from orders.realtime import broadcast_order_event
from restaurants.models import Restaurant
from staff.models import StaffUser
from tables.models import Table

from .models import Payment
from .views import PaymentSerializer, _restaurant


def _money(v) -> Decimal:
    try:
        return Decimal(str(v)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _complete_order(order: Order):
    now = timezone.now()
    order.status = 'completed'
    if not order.completed_at:
        order.completed_at = now
    order.save(update_fields=['status', 'completed_at', 'updated_at'])
    if order.table_id:
        table = order.table
        table.awaiting_bill = False
        table.needs_cleaning = True
        table.save(update_fields=['awaiting_bill', 'needs_cleaning'])
    return order


def _broadcast_completed(order: Order):
    order = (
        Order.objects.filter(pk=order.pk)
        .select_related('table', 'restaurant', 'served_by')
        .prefetch_related('items__menu_item')
        .first()
    )
    if not order:
        return
    slug = order.restaurant.slug if order.restaurant_id else 'surfues-resto'
    broadcast_order_event(slug, 'order.completed', serialize_kanban_card(order))


class PosCheckoutView(APIView):
    """
    Kassa: sifariş yarat + nağd/kart ödəniş (və ya mövcud sifarişi ödə).

    Body:
      method: cash | card_pos
      order_id?: mövcud aktiv sifariş
      — və ya yeni satış:
      items: [{menu_item_id, quantity}]
      table_id? / takeaway
      notes?
      amount_tendered?: nağd verilən məbləğ
      served_by_id?
      send_kitchen?: bool (default true) — KOT / WS
    """

    @transaction.atomic
    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        method = request.data.get('method', 'cash')
        if method not in ('cash', 'card_pos'):
            return Response(
                {'detail': 'Yalnız cash və ya card_pos'},
                status=400,
            )
        if method == 'cash' and not restaurant.accept_cash:
            return Response({'detail': 'Nağd qəbul edilmir'}, status=400)
        if method == 'card_pos' and not restaurant.accept_card:
            return Response({'detail': 'Kart qəbul edilmir'}, status=400)

        order_id = request.data.get('order_id')
        print_jobs = []
        created_new = False

        if order_id:
            order = (
                Order.objects.select_related('table', 'restaurant')
                .filter(pk=order_id, restaurant=restaurant)
                .first()
            )
            if not order:
                return Response({'detail': 'Sifariş tapılmadı'}, status=404)
            if order.status in ('completed', 'cancelled'):
                return Response(
                    {'detail': 'Bu sifariş artıq bağlanıb'},
                    status=400,
                )
            if order.payments.filter(status='paid').exists():
                return Response(
                    {'detail': 'Sifariş artıq ödənilib'},
                    status=400,
                )
        else:
            items_data = request.data.get('items') or []
            if not items_data:
                return Response({'detail': 'Səbət boşdur'}, status=400)

            takeaway = bool(request.data.get('takeaway')) or not request.data.get(
                'table_id'
            )
            table = None
            if not takeaway:
                table = Table.objects.filter(
                    pk=request.data.get('table_id'), restaurant=restaurant
                ).first()
                if not table:
                    return Response({'detail': 'Masa tapılmadı'}, status=404)

            item_ids = [int(x['menu_item_id']) for x in items_data]
            menu_map = {
                m.id: m
                for m in MenuItem.objects.filter(
                    restaurant=restaurant, pk__in=item_ids, is_active=True
                )
            }
            lines = []
            total = Decimal('0.00')
            for line in items_data:
                mid = int(line['menu_item_id'])
                menu_item = menu_map.get(mid)
                if not menu_item:
                    return Response(
                        {'detail': f'Məhsul tapılmadı: {mid}'}, status=400
                    )
                if not menu_item.is_available:
                    return Response(
                        {'detail': f'“{menu_item.name}” bitib'},
                        status=400,
                    )
                qty = max(1, int(line.get('quantity', 1)))
                unit = Decimal(menu_item.price)
                total += unit * qty
                lines.append((menu_item, qty, unit))

            served_by = None
            sid = request.data.get('served_by_id')
            if sid:
                served_by = StaffUser.objects.filter(
                    pk=sid, restaurant=restaurant, is_active=True
                ).first()

            order = Order.objects.create(
                restaurant=restaurant,
                table=table,
                source='pos',
                status='received',
                total_amount=total,
                notes=(request.data.get('notes') or '').strip(),
                served_by=served_by,
            )
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        menu_item=mi,
                        quantity=qty,
                        unit_price=unit,
                    )
                    for mi, qty, unit in lines
                ]
            )
            created_new = True

            if table:
                table.needs_cleaning = False
                table.awaiting_bill = False
                table.save(
                    update_fields=['needs_cleaning', 'awaiting_bill']
                )

            order = (
                Order.objects.filter(pk=order.pk)
                .select_related('table', 'restaurant')
                .prefetch_related('items__menu_item')
                .first()
            )

            send_kitchen = request.data.get('send_kitchen', True)
            if send_kitchen:
                from orders.views import _serialize_order, _slug_for

                payload = _serialize_order(order)
                broadcast_order_event(
                    _slug_for(restaurant), 'order.created', payload
                )
                if restaurant.uses_printer:
                    print_jobs = [
                        {
                            'id': j.id,
                            'printer': j.printer_id,
                            'status': j.status,
                        }
                        for j in enqueue_kitchen_tickets(order)
                    ]

        amount = Decimal(order.total_amount)
        if restaurant.service_charge_enabled and restaurant.service_charge_percent:
            amount = (
                amount
                * (1 + Decimal(restaurant.service_charge_percent) / Decimal(100))
            ).quantize(Decimal('0.01'))

        tendered = None
        change = Decimal('0.00')
        if method == 'cash':
            raw_tender = request.data.get('amount_tendered')
            if raw_tender is not None and str(raw_tender) != '':
                tendered = _money(raw_tender)
                if tendered < amount:
                    return Response(
                        {
                            'detail': 'Verilən məbləğ kifayət etmir',
                            'due': str(amount),
                            'tendered': str(tendered),
                        },
                        status=400,
                    )
                change = (tendered - amount).quantize(Decimal('0.01'))
            else:
                tendered = amount

        payment = Payment.objects.create(
            order=order,
            restaurant=restaurant,
            amount=amount,
            currency=restaurant.currency or 'AZN',
            method=method,
            gateway='',
            status='paid',
            paid_at=timezone.now(),
            raw_response={
                'pos': True,
                'amount_tendered': str(tendered) if tendered is not None else None,
                'change': str(change),
            },
        )

        order = _complete_order(order)
        _broadcast_completed(order)

        order = (
            Order.objects.filter(pk=order.pk)
            .select_related('table', 'restaurant')
            .prefetch_related('items__menu_item')
            .first()
        )

        receipt = build_receipt_payload(
            order,
            amount=amount,
            method=method,
            tendered=tendered,
            change=change,
        )
        receipt_job = enqueue_customer_receipt(
            order,
            amount=amount,
            method=method,
            tendered=tendered,
            change=change,
        )
        if receipt_job:
            print_jobs = list(print_jobs) + [
                {
                    'id': receipt_job.id,
                    'printer': receipt_job.printer_id,
                    'status': receipt_job.status,
                    'kind': 'receipt',
                }
            ]

        return Response(
            {
                'order_id': order.id,
                'created_new': created_new,
                'payment': PaymentSerializer(payment).data,
                'amount': str(amount),
                'amount_tendered': str(tendered) if tendered is not None else None,
                'change': str(change),
                'method': method,
                'receipt': receipt,
                'print_jobs': print_jobs,
            },
            status=201,
        )


class PosOpenChecksView(APIView):
    """Açıq masalar / ödənilməmiş sifarişlər — kassa üçün."""

    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        qs = (
            Order.objects.filter(
                restaurant=restaurant,
                status__in=('received', 'preparing', 'ready', 'delivering'),
            )
            .select_related('table')
            .prefetch_related('items__menu_item')
            .order_by('-created_at')[:40]
        )
        rows = []
        for o in qs:
            rows.append(
                {
                    'id': o.id,
                    'title': (
                        f'Masa {o.table.number}'
                        if o.table_id
                        else f'Al-apar #{o.id}'
                    ),
                    'table_id': o.table_id,
                    'status': o.status,
                    'status_label': o.get_status_display(),
                    'source': o.source,
                    'total_amount': str(o.total_amount),
                    'items': [
                        {
                            'name': i.menu_item.name,
                            'quantity': i.quantity,
                        }
                        for i in o.items.all()
                    ],
                }
            )
        return Response({'results': rows})
