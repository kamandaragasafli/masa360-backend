from django.contrib import admin

from .models import AccessToken, Device, StaffUser


@admin.register(StaffUser)
class StaffUserAdmin(admin.ModelAdmin):
    list_display = (
        'full_name',
        'restaurant',
        'role',
        'is_active',
        'has_pin',
        'can_discount',
        'can_edit_menu',
        'can_cancel_preparing_order',
    )
    list_filter = ('role', 'is_active', 'restaurant')
    search_fields = ('user__username', 'user__email', 'full_name')
    readonly_fields = ('pin_code',)

    @admin.display(boolean=True, description='PIN')
    def has_pin(self, obj):
        return obj.has_pin


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'is_active', 'last_seen_at', 'created_at')
    list_filter = ('is_active', 'restaurant')
    readonly_fields = ('token',)


@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    list_display = ('kind', 'restaurant', 'staff', 'created_at', 'expires_at')
    list_filter = ('kind',)
    readonly_fields = ('key',)
