from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order',
        'amount',
        'currency',
        'gateway',
        'status',
        'paid_at',
        'created_at',
    )
    list_filter = ('status', 'gateway', 'method')
    search_fields = ('gateway_transaction_id', 'gateway_invoice_id')
    readonly_fields = ('created_at', 'updated_at', 'raw_response')
