from django.conf import settings
from django.db import models
from django.utils import timezone


class Table(models.Model):
    SHAPE_ROUND = 'round'
    SHAPE_RECT = 'rect'
    SHAPE_CHOICES = [
        (SHAPE_ROUND, 'Dairəvi'),
        (SHAPE_RECT, 'Düzbucaqlı'),
    ]

    ZONE_CHOICES = [
        ('zal', 'Zal'),
        ('terras', 'Terras'),
        ('vip', 'VIP otaq'),
    ]

    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='tables',
    )
    number = models.CharField(max_length=10)
    capacity = models.PositiveIntegerField(default=4)
    shape = models.CharField(
        max_length=20,
        choices=SHAPE_CHOICES,
        default=SHAPE_ROUND,
    )
    zone = models.CharField(max_length=20, choices=ZONE_CHOICES, default='zal')
    pos_x = models.FloatField(default=50)
    pos_y = models.FloatField(default=50)
    width = models.FloatField(default=12)
    height = models.FloatField(default=12)
    rotation = models.FloatField(default=0)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True)
    qr_enabled = models.BooleanField(default=True)

    # Ofisiant qeydi və xidmət statusu
    notes = models.TextField(blank=True)
    needs_cleaning = models.BooleanField(default=False)
    awaiting_bill = models.BooleanField(default=False)
    split_bill = models.BooleanField(default=False)

    class Meta:
        ordering = ['number']
        unique_together = [['restaurant', 'number']]
        verbose_name = 'Masa'
        verbose_name_plural = 'Masalar'

    def __str__(self):
        return f'Masa {self.number} ({self.capacity} yer) — {self.restaurant}'


class FloorElement(models.Model):
    TYPE_CHOICES = [
        ('cashier', 'Kassa'),
        ('entry', 'Giriş'),
        ('exit', 'Çıxış'),
        ('stairs', 'Pilləkən'),
        ('restroom', 'Tualet'),
        ('wash', 'Əl yuma'),
        ('room', 'Otaq'),
        ('label', 'Yazı'),
    ]

    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='floor_elements',
    )
    element_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    label = models.CharField(max_length=100, blank=True)
    pos_x = models.FloatField(default=10)
    pos_y = models.FloatField(default=10)
    width = models.FloatField(default=12)
    height = models.FloatField(default=8)

    class Meta:
        verbose_name = 'Plan elementi'
        verbose_name_plural = 'Plan elementləri'

    def __str__(self):
        return f'{self.get_element_type_display()} ({self.restaurant})'


class Reservation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Gözləyir'),
        ('seated', 'Oturub'),
        ('cancelled', 'Ləğv'),
        ('completed', 'Tamamlanıb'),
    ]

    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='reservations',
    )
    table = models.ForeignKey(
        Table,
        on_delete=models.CASCADE,
        related_name='reservations',
    )
    guest_name = models.CharField(max_length=120)
    party_size = models.PositiveIntegerField(default=2)
    reserved_for = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['reserved_for']
        verbose_name = 'Rezervasiya'
        verbose_name_plural = 'Rezervasiyalar'

    def __str__(self):
        return f'Masa {self.table.number} — {self.guest_name} @ {self.reserved_for}'

    @property
    def is_upcoming(self):
        return self.status == 'pending' and self.reserved_for >= timezone.now()
