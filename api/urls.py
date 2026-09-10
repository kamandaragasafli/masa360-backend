from django.urls import include, path

from . import public, views
from .online_delivery import (
    DeliveryGeocodeView,
    DeliveryQuoteView,
    OnlineOrderCreateView,
)

urlpatterns = [
    path('health/', views.health, name='health'),
    path('public/menu/', public.PublicMenuView.as_view(), name='public-menu'),
    path(
        'public/resolve/',
        public.PublicResolveView.as_view(),
        name='public-resolve',
    ),
    path(
        'public/delivery/quote/',
        DeliveryQuoteView.as_view(),
        name='public-delivery-quote',
    ),
    path(
        'public/delivery/geocode/',
        DeliveryGeocodeView.as_view(),
        name='public-delivery-geocode',
    ),
    path(
        'public/delivery/orders/',
        OnlineOrderCreateView.as_view(),
        name='public-delivery-order',
    ),
    path('auth/', include('staff.urls')),
    path('restaurants/', include('restaurants.urls')),
    path('tables/', include('tables.urls')),
    path('menu/', include('menu.urls')),
    path('orders/', include('orders.urls')),
    path('payments/', include('payments.urls')),
    path('notifications/', include('notifications.urls')),
    path('delivery/', include('delivery.urls')),
    path('warehouse/', include('warehouse.urls')),
]
