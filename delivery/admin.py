from django.contrib import admin

from .models import Courier, DeliveryAssignment, Payout


@admin.register(Courier)
class CourierAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'display_name',
        'phone',
        'restaurant',
        'is_available',
        'last_location_update',
    )
    list_filter = ('is_available', 'restaurant')
    search_fields = ('full_name', 'phone')


@admin.register(DeliveryAssignment)
class DeliveryAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order',
        'courier',
        'status',
        'delivery_fee',
        'offered_at',
        'delivered_at',
    )
    list_filter = ('status', 'restaurant', 'confirmation_method')
    search_fields = ('dropoff_address', 'customer_phone', 'order__id')


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'courier',
        'period_start',
        'period_end',
        'total_amount',
        'is_paid',
    )
    list_filter = ('is_paid',)
