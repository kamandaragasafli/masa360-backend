import json

from channels.generic.websocket import AsyncWebsocketConsumer

from .realtime import kitchen_group, staff_group


class KitchenConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.slug = self.scope['url_route']['kwargs'].get('slug', 'surfues-resto')
        self.group = kitchen_group(self.slug)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def order_event(self, event):
        await self.send(
            text_data=json.dumps(
                {'event': event['event'], 'order': event['order']},
                default=str,
            )
        )

    async def notification_event(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    'event': 'notification.created',
                    'notification': event['notification'],
                },
                default=str,
            )
        )


class StaffConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.slug = self.scope['url_route']['kwargs'].get('slug', 'surfues-resto')
        self.group = staff_group(self.slug)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def order_event(self, event):
        await self.send(
            text_data=json.dumps(
                {'event': event['event'], 'order': event['order']},
                default=str,
            )
        )

    async def notification_event(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    'event': 'notification.created',
                    'notification': event['notification'],
                },
                default=str,
            )
        )
