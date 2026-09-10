from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def kitchen_group(slug: str) -> str:
    return f'kitchen_{slug or "surfues-resto"}'


def staff_group(slug: str) -> str:
    return f'staff_{slug or "surfues-resto"}'


def broadcast_order_event(slug: str, event_type: str, order_data: dict):
    """Mətbəx və ofisiant kanallarına sifariş hadisəsi göndər."""
    layer = get_channel_layer()
    if layer is None:
        return
    payload = {
        'type': 'order.event',
        'event': event_type,
        'order': order_data,
    }
    for group in (kitchen_group(slug), staff_group(slug)):
        async_to_sync(layer.group_send)(group, payload)
