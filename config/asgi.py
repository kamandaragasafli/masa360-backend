"""
ASGI config for config project — HTTP + WebSocket (Channels).
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()

from delivery.routing import websocket_urlpatterns as delivery_ws  # noqa: E402
from orders.routing import websocket_urlpatterns as order_ws  # noqa: E402

websocket_urlpatterns = order_ws + delivery_ws

application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
