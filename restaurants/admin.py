from django.contrib import admin

from .models import KitchenPrinter, Restaurant


class KitchenPrinterInline(admin.TabularInline):
    model = KitchenPrinter
    extra = 0


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'slug',
        'kitchen_mode',
        'phone',
        'is_active',
        'opening_time',
        'closing_time',
    )
    list_filter = ('is_active', 'kitchen_mode')
    search_fields = ('name', 'slug', 'address', 'phone')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [KitchenPrinterInline]


@admin.register(KitchenPrinter)
class KitchenPrinterAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'restaurant',
        'ip_address',
        'port',
        'is_active',
    )
    list_filter = ('is_active', 'restaurant')
    search_fields = ('name', 'ip_address')
