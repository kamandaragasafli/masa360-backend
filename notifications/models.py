from django.db import models


class Notification(models.Model):
    TYPE_CHOICES = [
        ('order_ready', 'Sifariş hazırdır'),
        ('waiter_call', 'Ofisiant çağırışı'),
        ('bill_request', 'Hesab istəyi'),
        ('new_order', 'Yeni sifariş'),
        ('new_qr_order', 'Yeni QR sifarişi'),
        ('order_cancelled', 'Sifariş ləğv edildi'),
        ('low_stock', 'Stok azalıb'),
        ('expiry_warning', 'Son istifadə tarixi'),
        ('payment_failed', 'Ödəniş uğursuz'),
        ('daily_summary', 'Gündəlik xülasə'),
        ('cancel_spike', 'Qeyri-adi ləğv sayı'),
        ('subscription_expiry', 'Abunəlik bitir'),
    ]
    PRIORITY_CHOICES = [
        ('critical', 'Kritik'),
        ('medium', 'Orta'),
        ('low', 'Aşağı'),
    ]
    ROLE_CHOICES = [
        ('waiter', 'Ofisiant'),
        ('kitchen', 'Mətbəx'),
        ('manager', 'Menecer'),
        ('courier', 'Kuryer'),
        ('all', 'Hamı'),
    ]

    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    recipient_role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default='manager'
    )
    recipient = models.ForeignKey(
        'staff.StaffUser',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default='medium'
    )
    title = models.CharField(max_length=120, blank=True, default='')
    message = models.CharField(max_length=255)
    link = models.CharField(max_length=200, blank=True, default='')
    related_order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    related_table = models.ForeignKey(
        'tables.Table',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['restaurant', 'is_read', '-created_at']),
            models.Index(fields=['restaurant', 'priority', '-created_at']),
        ]

    def __str__(self):
        return f'[{self.priority}] {self.type}: {self.message[:40]}'
