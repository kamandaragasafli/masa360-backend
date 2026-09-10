from django.db import models


class Category(models.Model):
    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='categories',
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    printer = models.ForeignKey(
        'restaurants.KitchenPrinter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='categories',
        help_text='Bu kateqoriyanın KOT ticket-ləri hansı printerə gedir',
    )

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Kateqoriya'
        verbose_name_plural = 'Kateqoriyalar'

    def __str__(self):
        return f'{self.name} ({self.restaurant})'


class MenuItem(models.Model):
    SPICY_CHOICES = [
        (0, 'Acısız'),
        (1, 'Yüngül'),
        (2, 'Orta'),
        (3, 'Acılı'),
    ]

    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='menu_items',
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='items',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    image_url = models.URLField(blank=True)  # Unsplash və s. xarici şəkil
    is_available = models.BooleanField(default=True)  # stokda var/yox
    is_active = models.BooleanField(default=True)  # menyuda görünür/gizli
    prep_time_minutes = models.PositiveIntegerField(default=15)
    is_vegan = models.BooleanField(default=False)
    is_gluten_free = models.BooleanField(default=False)
    spicy_level = models.PositiveSmallIntegerField(choices=SPICY_CHOICES, default=0)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Menyu məhsulu'
        verbose_name_plural = 'Menyu məhsulları'

    def __str__(self):
        return f'{self.name} — {self.price}'


class ModifierGroup(models.Model):
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name='modifier_groups',
    )
    name = models.CharField(max_length=100)  # "Ət seçimi", "Əlavələr"
    is_required = models.BooleanField(default=False)
    min_select = models.PositiveIntegerField(default=0)
    max_select = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Modifikator qrupu'
        verbose_name_plural = 'Modifikator qrupları'

    def __str__(self):
        return f'{self.name} ({self.menu_item})'


class Modifier(models.Model):
    group = models.ForeignKey(
        ModifierGroup,
        on_delete=models.CASCADE,
        related_name='options',
    )
    name = models.CharField(max_length=100)  # "Mal əti", "Əlavə pendir"
    extra_price = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    is_available = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Modifikator'
        verbose_name_plural = 'Modifikatorlar'

    def __str__(self):
        return f'{self.name} (+{self.extra_price})'
