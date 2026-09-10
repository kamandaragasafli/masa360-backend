"""
Bildiriş yaradılması: DB + WebSocket (paralel kanallar).
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from orders.realtime import kitchen_group, staff_group

from .models import Notification

# Tip → prioritet / rol / başlıq defaultları
TYPE_META = {
    'order_ready': {
        'priority': 'critical',
        'role': 'waiter',
        'title': 'Sifariş hazırdır',
    },
    'waiter_call': {
        'priority': 'critical',
        'role': 'waiter',
        'title': 'Ofisiant çağırışı',
    },
    'bill_request': {
        'priority': 'critical',
        'role': 'waiter',
        'title': 'Hesab istəyi',
    },
    'new_order': {
        'priority': 'critical',
        'role': 'kitchen',
        'title': 'Yeni sifariş',
    },
    'new_qr_order': {
        'priority': 'critical',
        'role': 'waiter',
        'title': 'Yeni QR sifarişi',
    },
    'order_cancelled': {
        'priority': 'critical',
        'role': 'kitchen',
        'title': 'Sifariş ləğv edildi',
    },
    'low_stock': {
        'priority': 'medium',
        'role': 'manager',
        'title': 'Stok azalıb',
    },
    'expiry_warning': {
        'priority': 'medium',
        'role': 'manager',
        'title': 'Son istifadə tarixi',
    },
    'payment_failed': {
        'priority': 'critical',
        'role': 'manager',
        'title': 'Ödəniş uğursuz',
    },
    'daily_summary': {
        'priority': 'low',
        'role': 'manager',
        'title': 'Gündəlik xülasə',
    },
    'cancel_spike': {
        'priority': 'medium',
        'role': 'manager',
        'title': 'Qeyri-adi ləğv sayı',
    },
    'subscription_expiry': {
        'priority': 'critical',
        'role': 'manager',
        'title': 'Abunəlik bitmək üzrədir',
    },
}


def serialize_notification(n: Notification) -> dict:
    return {
        'id': n.id,
        'type': n.type,
        'type_label': n.get_type_display(),
        'priority': n.priority,
        'priority_label': n.get_priority_display(),
        'recipient_role': n.recipient_role,
        'title': n.title or TYPE_META.get(n.type, {}).get('title', ''),
        'message': n.message,
        'link': n.link,
        'is_read': n.is_read,
        'created_at': n.created_at.isoformat(),
        'related_order_id': n.related_order_id,
        'related_table_id': n.related_table_id,
        'table_number': (
            n.related_table.number if n.related_table_id else None
        ),
    }


def _broadcast(restaurant, payload: dict):
    layer = get_channel_layer()
    if layer is None:
        return
    slug = getattr(restaurant, 'slug', None) or 'surfues-resto'
    event = {
        'type': 'notification.event',
        'notification': payload,
    }
    for group in (staff_group(slug), kitchen_group(slug)):
        async_to_sync(layer.group_send)(group, event)


def create_notification(
    *,
    restaurant,
    type: str,
    message: str,
    recipient_role: str | None = None,
    recipient=None,
    priority: str | None = None,
    title: str = '',
    link: str = '',
    related_order=None,
    related_table=None,
) -> Notification:
    meta = TYPE_META.get(type, {})
    n = Notification.objects.create(
        restaurant=restaurant,
        type=type,
        message=message[:255],
        title=(title or meta.get('title', ''))[:120],
        priority=priority or meta.get('priority', 'medium'),
        recipient_role=recipient_role or meta.get('role', 'manager'),
        recipient=recipient,
        link=link[:200],
        related_order=related_order,
        related_table=related_table,
    )
    payload = serialize_notification(n)
    # Atomic blokdan sonra göndər — WS client DB-ni oxuyanda hazır olsun
    transaction.on_commit(lambda: _broadcast(restaurant, payload))
    return n
