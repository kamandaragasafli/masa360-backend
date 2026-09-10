from django.contrib import admin

from .models import FloorElement, Reservation, Table


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = (
        'number',
        'restaurant',
        'zone',
        'capacity',
        'shape',
        'needs_cleaning',
        'awaiting_bill',
    )
    list_filter = ('restaurant', 'zone', 'shape', 'needs_cleaning', 'awaiting_bill')
    search_fields = ('number', 'notes')


@admin.register(FloorElement)
class FloorElementAdmin(admin.ModelAdmin):
    list_display = ('element_type', 'label', 'restaurant', 'pos_x', 'pos_y')
    list_filter = ('element_type', 'restaurant')


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        'guest_name',
        'table',
        'reserved_for',
        'party_size',
        'status',
        'restaurant',
    )
    list_filter = ('status', 'restaurant')
    search_fields = ('guest_name', 'table__number')
