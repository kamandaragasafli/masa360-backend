import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from .services import courier_group, tracking_group


class CourierConsumer(AsyncWebsocketConsumer):
    """Kuryerə təklif push + lokasiya qəbulu."""

    async def connect(self):
        self.courier_id = int(self.scope['url_route']['kwargs']['courier_id'])
        self.group = courier_group(self.courier_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if data.get('type') == 'location':
            lat = data.get('lat')
            lng = data.get('lng')
            order_id = data.get('order_id')
            if lat is None or lng is None:
                return
            await self._update_location(float(lat), float(lng))
            if order_id:
                await self.channel_layer.group_send(
                    tracking_group(int(order_id)),
                    {
                        'type': 'location.update',
                        'lat': float(lat),
                        'lng': float(lng),
                        'order_id': int(order_id),
                    },
                )

    async def courier_event(self, event):
        await self.send(
            text_data=json.dumps(
                {'event': event['event'], 'payload': event['payload']},
                default=str,
            )
        )

    @database_sync_to_async
    def _update_location(self, lat: float, lng: float):
        from .models import Courier

        Courier.objects.filter(id=self.courier_id).update(
            current_lat=lat,
            current_lng=lng,
            last_location_update=timezone.now(),
        )


class OrderTrackingConsumer(AsyncWebsocketConsumer):
    """Müştəri canlı izləmə (gələcək app üçün infrastruktur)."""

    async def connect(self):
        self.order_id = int(self.scope['url_route']['kwargs']['order_id'])
        self.group = tracking_group(self.order_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def location_update(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    'event': 'location.update',
                    'lat': event['lat'],
                    'lng': event['lng'],
                    'order_id': event.get('order_id'),
                }
            )
        )
