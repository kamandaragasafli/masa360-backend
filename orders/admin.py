from django.contrib import admin

from .models import Order, OrderItem, PrintJob


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'restaurant',
        'table',
        'status',
        'source',
        'total_amount',
        'created_at',
    )
    list_filter = ('status', 'source', 'restaurant')
    inlines = [OrderItemInline]


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'printer',
        'order',
        'status',
        'is_test',
        'created_at',
    )
    list_filter = ('status', 'is_test', 'printer')
    search_fields = ('error_message',)
