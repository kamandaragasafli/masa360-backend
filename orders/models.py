from django.db import models
from django.utils import timezone


class Order(models.Model):
    STATUS_CHOICES = [
        ('received', 'Qəbul edildi'),
        ('preparing', 'Hazırlanır'),
        ('ready', 'Hazırdır'),
        ('delivering', 'Çatdırılır'),
        ('completed', 'Tamamlandı'),
        ('cancelled', 'Ləğv edildi'),
    ]
    SOURCE_CHOICES = [
        ('qr', 'QR Menyu'),
        ('waiter', 'Ofisiant'),
        ('pos', 'Kassa'),
        ('mobile_app', 'Mobil tətbiq'),
        ('online', 'Onlayn sayt'),
    ]
    ORDER_TYPE_CHOICES = [
        ('dine_in', 'Masada'),
        ('takeaway', 'Al-apar'),
        ('delivery', 'Çatdırılma'),
    ]
    CANCEL_REASON_CHOICES = [
        ('', '—'),
        ('customer', 'Müştəri ləğv etdi'),
        ('stock', 'Stok yoxdur'),
        ('kitchen', 'Mətbəx bacarmadı'),
        ('error', 'Xəta / yanlış sifariş'),
        ('timeout', 'Vaxt bitdi'),
        ('other', 'Digər'),
    ]

    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='orders',
    )
    table = models.ForeignKey(
        'tables.Table',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    order_type = models.CharField(
        max_length=20,
        choices=ORDER_TYPE_CHOICES,
        default='dine_in',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='received',
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)
    guest_phone = models.CharField(max_length=30, blank=True, default='')

    # Çatdırılma — yalnız order_type='delivery'
    delivery_address = models.CharField(max_length=500, blank=True, default='')
    delivery_lat = models.FloatField(null=True, blank=True)
    delivery_lng = models.FloatField(null=True, blank=True)
    customer_name = models.CharField(max_length=100, blank=True, default='')
    customer_phone = models.CharField(max_length=20, blank=True, default='')
    delivery_note = models.CharField(max_length=255, blank=True, default='')
    delivery_fee = models.DecimalField(
        max_digits=8, decimal_places=2, default=0
    )
    delivery_distance_km = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    delivery_payment_method = models.CharField(
        max_length=20,
        blank=True,
        default='cash_on_delivery',
        help_text='cash_on_delivery | card_later',
    )
    cancelled_reason = models.CharField(
        max_length=30,
        choices=CANCEL_REASON_CHOICES,
        blank=True,
        default='',
    )
    cancelled_note = models.CharField(max_length=255, blank=True, default='')
    served_by = models.ForeignKey(
        'staff.StaffUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='served_orders',
    )

    # Status keçidlərində avtomatik doldurulur
    preparing_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Sifariş'
        verbose_name_plural = 'Sifarişlər'
        indexes = [
            models.Index(fields=['restaurant', 'created_at']),
            models.Index(fields=['restaurant', 'status']),
        ]

    def __str__(self):
        return f'#{self.pk} — {self.restaurant} ({self.get_status_display()})'

    def apply_status_timestamp(self, new_status):
        """Status keçidində vaxt möhürü yaz."""
        now = timezone.now()
        if new_status == 'preparing' and not self.preparing_at:
            self.preparing_at = now
        elif new_status == 'ready' and not self.ready_at:
            self.ready_at = now
        elif new_status == 'completed' and not self.completed_at:
            self.completed_at = now
        elif new_status == 'cancelled' and not self.cancelled_at:
            self.cancelled_at = now


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
    )
    menu_item = models.ForeignKey(
        'menu.MenuItem',
        on_delete=models.PROTECT,
        related_name='order_items',
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)  # sifariş anındakı qiymət
    special_instructions = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Sifariş məhsulu'
        verbose_name_plural = 'Sifariş məhsulları'

    def __str__(self):
        return f'{self.menu_item} × {self.quantity}'

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class PrintJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Gözləyir'),
        ('printing', 'Çap olunur'),
        ('success', 'Uğurlu'),
        ('failed', 'Uğursuz'),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='print_jobs',
        null=True,
        blank=True,
    )
    printer = models.ForeignKey(
        'restaurants.KitchenPrinter',
        on_delete=models.CASCADE,
        related_name='print_jobs',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    error_message = models.TextField(blank=True)
    # Ticket məzmunu (reprint üçün snapshot)
    payload = models.JSONField(default=dict, blank=True)
    is_test = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Çap işi'
        verbose_name_plural = 'Çap işləri'

    def __str__(self):
        return f'PrintJob #{self.pk} — {self.printer} ({self.status})'
