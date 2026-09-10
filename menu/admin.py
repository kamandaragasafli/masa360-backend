from django.contrib import admin

from .models import Category, MenuItem, Modifier, ModifierGroup


class ModifierInline(admin.TabularInline):
    model = Modifier
    extra = 0


class ModifierGroupInline(admin.TabularInline):
    model = ModifierGroup
    extra = 0
    show_change_link = True


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'printer', 'order', 'is_active')
    list_filter = ('restaurant', 'is_active', 'printer')
    search_fields = ('name',)
    list_editable = ('printer',)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'restaurant',
        'category',
        'price',
        'is_available',
        'is_active',
        'prep_time_minutes',
    )
    list_filter = ('restaurant', 'category', 'is_available', 'is_active')
    search_fields = ('name', 'description')
    inlines = [ModifierGroupInline]


@admin.register(ModifierGroup)
class ModifierGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'menu_item', 'is_required', 'min_select', 'max_select')
    inlines = [ModifierInline]


@admin.register(Modifier)
class ModifierAdmin(admin.ModelAdmin):
    list_display = ('name', 'group', 'extra_price', 'is_available')
