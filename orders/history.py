"""Tarixçə — filtr, detal, statistika, Excel export."""

from datetime import datetime, time, timedelta
from io import BytesIO

from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from openpyxl import Workbook
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.services import create_notification
from restaurants.tenancy import resolve_restaurant

from .models import Order, OrderItem
from .realtime import broadcast_order_event


def _restaurant(request):
    return resolve_restaurant(request)


def _parse_range(request):
    """Preset və ya from/to tarixləri."""
    preset = request.query_params.get('preset', '')
    now = timezone.localtime()
    today = now.date()

    if preset == 'today':
        start, end = today, today
    elif preset == 'yesterday':
        start = today - timedelta(days=1)
        end = start
    elif preset == 'week':
        start = today - timedelta(days=today.weekday())
        end = today
    elif preset == 'month':
        start = today.replace(day=1)
        end = today
    else:
        start = parse_date(request.query_params.get('date_from') or '') or (
            today - timedelta(days=7)
        )
        end = parse_date(request.query_params.get('date_to') or '') or today

    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(start, time.min), tz)
    end_dt = timezone.make_aware(datetime.combine(end, time.max), tz)
    return start_dt, end_dt, start, end


def _filtered_orders(request, restaurant, *, for_stats=False):
    start_dt, end_dt, start, end = _parse_range(request)
    qs = Order.objects.filter(
        restaurant=restaurant,
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).select_related('table', 'served_by')

    if not for_stats:
        qs = qs.prefetch_related('items__menu_item', 'payments').annotate(
            items_count=Count('items', distinct=True)
        )

    status = request.query_params.get('status')
    if status and status != 'all':
        if status == 'history':
            qs = qs.filter(status__in=('completed', 'cancelled'))
        else:
            qs = qs.filter(status=status)

    source = request.query_params.get('source')
    if source and source != 'all':
        qs = qs.filter(source=source)

    zone = request.query_params.get('zone')
    if zone and zone != 'all':
        qs = qs.filter(table__zone=zone)

    table_id = request.query_params.get('table')
    if table_id:
        qs = qs.filter(table_id=table_id)

    q = (request.query_params.get('search') or '').strip()
    if q:
        q_filter = Q(guest_phone__icontains=q) | Q(notes__icontains=q)
        if q.lstrip('#').isdigit():
            q_filter |= Q(pk=int(q.lstrip('#')))
        qs = qs.filter(q_filter)

    return qs.order_by('-created_at'), start, end


def _duration_minutes(start, end):
    if not start or not end:
        return None
    return max(0, int((end - start).total_seconds() // 60))


def serialize_order_row(order):
    title = (
        f'Masa {order.table.number}'
        if order.table_id
        else f'Al-apar'
    )
    payment = None
    payments = list(order.payments.all()) if hasattr(order, 'payments') else []
    paid = next((p for p in payments if p.status == 'paid'), None) or (
        payments[0] if payments else None
    )
    if paid:
        payment = {
            'method': paid.method,
            'method_label': paid.get_method_display(),
            'status': paid.status,
            'gateway': paid.gateway,
        }

    return {
        'id': order.id,
        'created_at': order.created_at.isoformat(),
        'time': timezone.localtime(order.created_at).strftime('%H:%M'),
        'date': timezone.localtime(order.created_at).strftime('%d.%m.%Y'),
        'title': title,
        'table_number': order.table.number if order.table_id else None,
        'zone': order.table.zone if order.table_id else None,
        'items_count': getattr(order, 'items_count', order.items.count()),
        'total_amount': str(order.total_amount),
        'status': order.status,
        'status_label': order.get_status_display(),
        'source': order.source,
        'source_label': order.get_source_display(),
        'served_by_name': (
            order.served_by.full_name if order.served_by_id else ''
        ),
        'guest_phone': order.guest_phone,
        'cancelled_reason': order.cancelled_reason,
        'cancelled_reason_label': order.get_cancelled_reason_display()
        if order.cancelled_reason
        else '',
        'cancelled_note': order.cancelled_note,
        'payment': payment,
    }


def serialize_order_detail(order):
    row = serialize_order_row(order)
    row['notes'] = order.notes
    row['items'] = [
        {
            'id': i.id,
            'name': i.menu_item.name,
            'quantity': i.quantity,
            'unit_price': str(i.unit_price),
            'line_total': str(i.line_total),
            'special_instructions': i.special_instructions,
        }
        for i in order.items.all()
    ]
    row['timeline'] = {
        'created_at': order.created_at.isoformat(),
        'preparing_at': order.preparing_at.isoformat()
        if order.preparing_at
        else None,
        'ready_at': order.ready_at.isoformat() if order.ready_at else None,
        'completed_at': order.completed_at.isoformat()
        if order.completed_at
        else None,
        'cancelled_at': order.cancelled_at.isoformat()
        if order.cancelled_at
        else None,
        'prep_minutes': _duration_minutes(
            order.preparing_at or order.created_at, order.ready_at
        ),
        'total_minutes': _duration_minutes(
            order.created_at, order.completed_at or order.cancelled_at
        ),
    }
    return row


class HistoryListView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        qs, start, end = _filtered_orders(request, restaurant)
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(100, max(10, int(request.query_params.get('page_size', 30))))
        total = qs.count()
        offset = (page - 1) * page_size
        rows = [serialize_order_row(o) for o in qs[offset : offset + page_size]]

        return Response(
            {
                'count': total,
                'page': page,
                'page_size': page_size,
                'date_from': start.isoformat(),
                'date_to': end.isoformat(),
                'results': rows,
            }
        )


class HistoryDetailView(APIView):
    def get(self, request, pk):
        restaurant = _restaurant(request)
        order = (
            Order.objects.filter(pk=pk, restaurant=restaurant)
            .select_related('table', 'served_by')
            .prefetch_related('items__menu_item', 'payments')
            .first()
        )
        if not order:
            return Response({'detail': 'Sifariş tapılmadı'}, status=404)
        order.items_count = order.items.count()
        return Response(serialize_order_detail(order))


class HistoryStatsView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        qs, start, end = _filtered_orders(request, restaurant, for_stats=True)
        completed = qs.filter(status='completed')
        cancelled = qs.filter(status='cancelled')

        cancel_reasons = list(
            cancelled.exclude(cancelled_reason='')
            .values('cancelled_reason')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        reason_map = dict(Order.CANCEL_REASON_CHOICES)
        cancel_reasons = [
            {
                'reason': r['cancelled_reason'],
                'label': reason_map.get(
                    r['cancelled_reason'], r['cancelled_reason']
                ),
                'count': r['count'],
            }
            for r in cancel_reasons
        ]

        staff_stats = list(
            completed.filter(served_by__isnull=False)
            .values('served_by_id', 'served_by__full_name')
            .annotate(
                orders=Count('id'),
                revenue=Sum('total_amount'),
            )
            .order_by('-orders')[:10]
        )

        top_cancelled_items = list(
            OrderItem.objects.filter(order__in=cancelled)
            .values('menu_item__name')
            .annotate(count=Sum('quantity'))
            .order_by('-count')[:8]
        )

        revenue = completed.aggregate(
            total=Coalesce(
                Sum('total_amount'),
                Value(Decimal('0')),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )['total']

        return Response(
            {
                'date_from': start.isoformat(),
                'date_to': end.isoformat(),
                'orders_total': qs.count(),
                'orders_completed': completed.count(),
                'orders_cancelled': cancelled.count(),
                'revenue': str(revenue),
                'cancel_reasons': cancel_reasons,
                'staff_performance': [
                    {
                        'id': s['served_by_id'],
                        'name': s['served_by__full_name'] or '—',
                        'orders': s['orders'],
                        'revenue': str(s['revenue'] or 0),
                    }
                    for s in staff_stats
                ],
                'top_cancelled_items': [
                    {
                        'name': i['menu_item__name'],
                        'count': i['count'],
                    }
                    for i in top_cancelled_items
                ],
            }
        )


class HistoryExportExcelView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        qs, start, end = _filtered_orders(request, restaurant)
        wb = Workbook()
        ws = wb.active
        ws.title = 'Sifarisler'
        ws.append(
            [
                'Sifariş №',
                'Tarix',
                'Vaxt',
                'Masa/Növ',
                'Zona',
                'Mənbə',
                'Məhsul sayı',
                'Məbləğ',
                'Status',
                'Ofisiant',
                'Telefon',
                'Ləğv səbəbi',
            ]
        )
        for o in qs[:2000]:
            row = serialize_order_row(o)
            ws.append(
                [
                    o.id,
                    row['date'],
                    row['time'],
                    row['title'],
                    row.get('zone') or '',
                    row['source_label'],
                    row['items_count'],
                    float(o.total_amount),
                    row['status_label'],
                    row['served_by_name'],
                    row['guest_phone'],
                    row['cancelled_reason_label'],
                ]
            )

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        filename = f'tarixce-{start.isoformat()}-{end.isoformat()}.xlsx'
        resp = HttpResponse(
            buf.getvalue(),
            content_type=(
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ),
        )
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp


class OrderCancelView(APIView):
    """Sifarişi ləğv et + səbəb."""

    def post(self, request, pk):
        restaurant = _restaurant(request)
        order = Order.objects.filter(pk=pk, restaurant=restaurant).first()
        if not order:
            return Response({'detail': 'Sifariş tapılmadı'}, status=404)
        if order.status in ('completed', 'cancelled'):
            return Response({'detail': 'Bu sifariş ləğv edilə bilməz'}, status=400)

        reason = request.data.get('cancelled_reason', 'other')
        if reason not in dict(Order.CANCEL_REASON_CHOICES):
            reason = 'other'
        order.status = 'cancelled'
        order.cancelled_reason = reason
        order.cancelled_note = (request.data.get('cancelled_note') or '')[:255]
        order.apply_status_timestamp('cancelled')
        order.save(
            update_fields=[
                'status',
                'cancelled_reason',
                'cancelled_note',
                'cancelled_at',
                'updated_at',
            ]
        )
        table_label = (
            f'Masa {order.table.number}'
            if order.table_id
            else f'Sifariş #{order.id}'
        )
        create_notification(
            restaurant=order.restaurant,
            type='order_cancelled',
            message=f'{table_label} ləğv edildi — dayandırın',
            link='/kitchen',
            related_order=order,
            related_table=order.table,
        )
        order = (
            Order.objects.filter(pk=order.pk)
            .select_related('table', 'served_by')
            .prefetch_related('items__menu_item')
            .first()
        )
        from .kanban import serialize_kanban_card

        broadcast_order_event(
            order.restaurant.slug if order.restaurant_id else 'surfues-resto',
            'order.cancelled',
            serialize_kanban_card(order),
        )
        return Response(serialize_order_detail(order))
