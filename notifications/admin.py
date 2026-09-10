from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'type',
        'priority',
        'recipient_role',
        'message',
        'is_read',
        'created_at',
        'restaurant',
    )
    list_filter = ('type', 'priority', 'recipient_role', 'is_read', 'restaurant')
    search_fields = ('message', 'title')
