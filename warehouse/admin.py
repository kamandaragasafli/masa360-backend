from django.contrib import admin

from .models import (
    IngredientBatch,
    IngredientCategory,
    RawIngredient,
    Recipe,
    RecipeLine,
    WasteLog,
)


@admin.register(IngredientCategory)
class IngredientCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'order', 'is_active')
    list_filter = ('restaurant',)


@admin.register(RawIngredient)
class RawIngredientAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'category', 'unit', 'min_stock', 'is_active')
    list_filter = ('restaurant', 'unit')
    search_fields = ('name',)


@admin.register(IngredientBatch)
class IngredientBatchAdmin(admin.ModelAdmin):
    list_display = (
        'ingredient',
        'remaining_quantity',
        'quantity',
        'expiry_date',
        'supplier',
        'received_at',
    )
    list_filter = ('expiry_date',)
    search_fields = ('ingredient__name', 'supplier')


@admin.register(WasteLog)
class WasteLogAdmin(admin.ModelAdmin):
    list_display = ('batch', 'quantity', 'reason', 'created_at')
    list_filter = ('reason',)


class RecipeLineInline(admin.TabularInline):
    model = RecipeLine
    extra = 1


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('menu_item', 'updated_at')
    inlines = [RecipeLineInline]
