from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Courier(models.Model):
    """Restoranın öz kuryeri — StaffUser(role=courier) ilə 1:1."""

    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='couriers',
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='courier_profile',
        null=True,
        blank=True,
    )
    staff = models.OneToOneField(
        'staff.StaffUser',
        on_delete=models.CASCADE,
        related_name='courier_profile',
    )
    full_name = models.CharField(max_length=120, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    is_available = models.BooleanField(default=False)
    current_lat = models.FloatField(null=True, blank=True)
    current_lng = models.FloatField(null=True, blank=True)
    last_location_update = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Kuryer'
        verbose_name_plural = 'Kuryerlər'

    def __str__(self):
        return self.display_name

    def clean(self):
        if self.staff_id and self.restaurant_id:
            if self.staff.restaurant_id != self.restaurant_id:
                raise ValidationError(
                    'Kuryer işçisi başqa restoranadır'
                )
            if self.staff.role != 'courier':
                raise ValidationError('İşçi rolu kuryer olmalıdır')

    @property
    def display_name(self):
        if self.full_name.strip():
            return self.full_name.strip()
        if self.staff_id and self.staff.full_name:
            return self.staff.full_name
        if self.user_id:
            return self.user.get_full_name() or self.user.username
        return f'Kuryer #{self.pk}'


class DeliveryAssignment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Kuryer axtarılır'),
        ('offered', 'Təklif edildi'),
        ('accepted', 'Qəbul edildi'),
        ('picked_up', 'Götürüldü'),
        ('delivered', 'Çatdırıldı'),
        ('failed', 'Uğursuz — kuryer tapılmadı'),
        ('cancelled', 'Ləğv'),
    ]
    CONFIRM_CHOICES = [
        ('otp', 'OTP kod'),
        ('photo', 'Foto'),
    ]

    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='delivery',
    )
    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='deliveries',
    )
    courier = models.ForeignKey(
        Courier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    pickup_address = models.CharField(max_length=255, blank=True, default='')
    pickup_lat = models.FloatField(null=True, blank=True)
    pickup_lng = models.FloatField(null=True, blank=True)
    dropoff_address = models.CharField(max_length=255, blank=True, default='')
    dropoff_lat = models.FloatField(null=True, blank=True)
    dropoff_lng = models.FloatField(null=True, blank=True)
    customer_phone = models.CharField(max_length=30, blank=True, default='')
    customer_name = models.CharField(max_length=120, blank=True, default='')
    distance_km = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    eta_minutes = models.PositiveIntegerField(null=True, blank=True)
    offered_at = models.DateTimeField(null=True, blank=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    confirmation_method = models.CharField(
        max_length=10, choices=CONFIRM_CHOICES, default='otp'
    )
    confirmation_otp = models.CharField(max_length=4, blank=True, default='')
    confirmation_photo = models.ImageField(
        upload_to='delivery_proofs/', blank=True, null=True
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Çatdırılma tapşırığı'
        verbose_name_plural = 'Çatdırılma tapşırıqları'
        indexes = [
            models.Index(fields=['restaurant', 'status']),
            models.Index(fields=['courier', 'status']),
        ]

    def __str__(self):
        return f'Delivery #{self.pk} · order {self.order_id} ({self.status})'

    def clean(self):
        if self.courier_id and self.order_id:
            if self.courier.restaurant_id != self.order.restaurant_id:
                raise ValidationError(
                    'Kuryer sifarişin restoranına aid deyil'
                )
        if self.restaurant_id and self.order_id:
            if self.restaurant_id != self.order.restaurant_id:
                raise ValidationError(
                    'Çatdırılma restorani sifarişlə uyğun gəlmir'
                )


class Payout(models.Model):
    courier = models.ForeignKey(
        Courier, on_delete=models.CASCADE, related_name='payouts'
    )
    period_start = models.DateField()
    period_end = models.DateField()
    total_deliveries = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_end']
        verbose_name = 'Kuryer ödənişi'
        verbose_name_plural = 'Kuryer ödənişləri'

    def __str__(self):
        return f'Payout {self.courier_id} {self.period_start}–{self.period_end}'
