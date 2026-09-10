from django.urls import path

from .views import (
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    NotificationUnreadCountView,
)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path(
        'unread-count/',
        NotificationUnreadCountView.as_view(),
        name='notification-unread',
    ),
    path(
        'mark-all-read/',
        NotificationMarkAllReadView.as_view(),
        name='notification-mark-all',
    ),
    path(
        '<int:pk>/read/',
        NotificationMarkReadView.as_view(),
        name='notification-read',
    ),
]
