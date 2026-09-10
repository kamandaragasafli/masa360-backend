"""Kanban sifariş lövhəsi — canlı izləmə (admin yalnız baxır)."""

from datetime import datetime, time

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.tenancy import resolve_restaurant

from .models import Order, OrderItem

LIVE_STATUSES = ('received', 'preparing', 'ready', 'delivering')
COMPLETED_PREVIEW = 2

SOURCE_SHORT = {
    'qr': 'QR',
    'waiter': 'Ofisiant',
    'pos': 'Kassa',
    'mobile_app': 'App',
    'online': 'Onlayn',
}


def _restaurant(request):
    return resolve_restaurant(request)


def serialize_kanban_card(order: Order) -> dict:
    items = [
        {
            'name': i.menu_item.name if i.menu_item_id else '—',
            'quantity': i.quantity,
        }
        for i in order.items.all()
    ]
    age = max(0, int((timezone.now() - order.created_at).total_seconds()))
    completed_clock = None
    if order.completed_at:
        completed_clock = timezone.localtime(order.completed_at).strftime('%H:%M')

    title = (
        f'Masa {order.table.number}'
        if order.table_id and order.table
        else f'Al-apar #{order.pk}'
    )
    if order.order_type == 'delivery' or (
        order.source in ('mobile_app', 'online') and not order.table_id
    ):
        title = f'Çatdırılma #{order.pk}'

    source_tag = SOURCE_SHORT.get(order.source, order.get_source_display())

    return {
        'id': order.id,
        'title': title,
        'table_id': order.table_id,
        'table_number': order.table.number if order.table_id else None,
        'status': order.status,
        'source': order.source,
        'source_tag': source_tag,
        'order_type': order.order_type,
        'delivery_address': order.delivery_address or '',
        'customer_name': order.customer_name or '',
        'customer_phone': order.customer_phone or order.guest_phone or '',
        'total_amount': str(order.total_amount),
        'items': items,
        'age_seconds': age,
        'created_at': order.created_at.isoformat(),
        'completed_at': order.completed_at.isoformat()
        if order.completed_at
        else None,
        'completed_clock': completed_clock,
        'ready_at': order.ready_at.isoformat() if order.ready_at else None,
    }


def _orders_qs(restaurant):
    return (
        Order.objects.filter(restaurant=restaurant)
        .select_related('table', 'served_by')
        .prefetch_related(
            Prefetch(
                'items',
                queryset=OrderItem.objects.select_related('menu_item'),
            )
        )
    )


class KanbanBoardView(APIView):
    """
    GET — sütunlar üzrə kartlar.
    Tamamlandı: yalnız bugünkü, preview=2 + more say.
    """

    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        today = timezone.localdate()
        start = timezone.make_aware(datetime.combine(today, time.min))
        end = timezone.make_aware(datetime.combine(today, time.max))

        qs = _orders_qs(restaurant)
        live = qs.filter(status__in=LIVE_STATUSES).order_by('created_at')
        completed_qs = qs.filter(
            status='completed',
            completed_at__gte=start,
            completed_at__lte=end,
        ).order_by('-completed_at')
        completed_total = completed_qs.count()
        completed_preview = list(completed_qs[:COMPLETED_PREVIEW])

        columns = {
            'received': [],
            'preparing': [],
            'ready': [],
            'delivering': [],
        }
        for o in live:
            if o.status in columns:
                columns[o.status].append(serialize_kanban_card(o))

        return Response(
            {
                'columns': {
                    **columns,
                    'completed': {
                        'items': [
                            serialize_kanban_card(o) for o in completed_preview
                        ],
                        'total': completed_total,
                        'more': max(0, completed_total - len(completed_preview)),
                    },
                },
                'counts': {
                    'received': len(columns['received']),
                    'preparing': len(columns['preparing']),
                    'ready': len(columns['ready']),
                    'delivering': len(columns['delivering']),
                    'completed': completed_total,
                },
            }
        )
