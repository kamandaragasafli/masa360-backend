from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class IngredientCategory(models.Model):
    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='ingredient_categories',
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Xammal kateqoriyası'
        verbose_name_plural = 'Xammal kateqoriyaları'
        unique_together = ('restaurant', 'name')

    def __str__(self):
        return self.name


class RawIngredient(models.Model):
    UNIT_CHOICES = [
        ('kg', 'kq'),
        ('g', 'q'),
        ('l', 'litr'),
        ('ml', 'ml'),
        ('pcs', 'ədəd'),
    ]

    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='ingredients',
    )
    category = models.ForeignKey(
        IngredientCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ingredients',
    )
    name = models.CharField(max_length=120)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='kg')
    min_stock = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('1'),
        help_text='Kritik stok həddi (bu vahiddə)',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Xammal'
        verbose_name_plural = 'Xammallar'
        unique_together = ('restaurant', 'name')

    def __str__(self):
        return f'{self.name} ({self.get_unit_display()})'

    @property
    def total_remaining(self) -> Decimal:
        agg = self.batches.filter(remaining_quantity__gt=0).aggregate(
            t=Sum('remaining_quantity')
        )
        return agg['t'] or Decimal('0')


class IngredientBatch(models.Model):
    ingredient = models.ForeignKey(
        RawIngredient,
        on_delete=models.CASCADE,
        related_name='batches',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    remaining_quantity = models.DecimalField(max_digits=10, decimal_places=3)
    expiry_date = models.DateField(null=True, blank=True)
    supplier = models.CharField(max_length=120, blank=True, default='')
    invoice_image = models.ImageField(
        upload_to='warehouse/invoices/%Y/%m/',
        blank=True,
        null=True,
    )
    note = models.CharField(max_length=255, blank=True, default='')
    received_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_batches',
    )

    class Meta:
        ordering = ['expiry_date', 'received_at']
        verbose_name = 'Partiya'
        verbose_name_plural = 'Partiyalar'

    def __str__(self):
        return f'{self.ingredient.name} · {self.remaining_quantity}'

    def clean(self):
        if self.remaining_quantity is not None and self.quantity is not None:
            if self.remaining_quantity > self.quantity:
                raise ValidationError('Qalan miqdar qəbul miqdarından çox ola bilməz')
            if self.remaining_quantity < 0:
                raise ValidationError('Qalan miqdar mənfi ola bilməz')

    def save(self, *args, **kwargs):
        if self.remaining_quantity is None and self.quantity is not None:
            self.remaining_quantity = self.quantity
        super().save(*args, **kwargs)


class WasteLog(models.Model):
    REASON_CHOICES = [
        ('spoiled', 'Xarab oldu'),
        ('spilled', 'Düşdü / töküldü'),
        ('expired', 'Son tarix keçdi'),
        ('other', 'Digər'),
    ]

    batch = models.ForeignKey(
        IngredientBatch,
        on_delete=models.CASCADE,
        related_name='waste_logs',
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    note = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='waste_logs',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'İtki'
        verbose_name_plural = 'İtkilər'

    def __str__(self):
        return f'İtki {self.quantity} · {self.batch_id}'


class Recipe(models.Model):
    """MenuItem → xammal resepti (2-ci addım UI)."""

    menu_item = models.OneToOneField(
        'menu.MenuItem',
        on_delete=models.CASCADE,
        related_name='recipe',
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Resept'
        verbose_name_plural = 'Reseptlər'

    def __str__(self):
        return f'Resept · {self.menu_item_id}'


class RecipeLine(models.Model):
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    ingredient = models.ForeignKey(
        RawIngredient,
        on_delete=models.PROTECT,
        related_name='recipe_lines',
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        help_text='1 porsiya üçün miqdar (ingredient.unit)',
    )

    class Meta:
        unique_together = ('recipe', 'ingredient')
        verbose_name = 'Resept sətri'
        verbose_name_plural = 'Resept sətrləri'

    def __str__(self):
        return f'{self.ingredient_id} × {self.quantity}'
