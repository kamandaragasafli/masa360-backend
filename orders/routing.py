from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r'ws/kitchen/(?P<slug>[\w-]+)/$',
        consumers.KitchenConsumer.as_asgi(),
    ),
    re_path(
        r'ws/staff/(?P<slug>[\w-]+)/$',
        consumers.StaffConsumer.as_asgi(),
    ),
]
