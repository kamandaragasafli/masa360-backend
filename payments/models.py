from django.db import models
from django.utils import timezone


class Payment(models.Model):
    """
    Sifariş ödənişi — kart datası burada SAXLANMIR.
    Yalnız gateway tranzaksiya meta-məlumatı.
    """

    STATUS_CHOICES = [
        ('pending', 'Gözləyir'),
        ('processing', 'Emal olunur'),
        ('paid', 'Ödənilib'),
        ('failed', 'Uğursuz'),
        ('expired', 'Vaxtı bitib'),
        ('cancelled', 'Ləğv edilib'),
        ('refunded', 'Geri qaytarılıb'),
    ]
    METHOD_CHOICES = [
        ('cash', 'Nağd'),
        ('card_pos', 'POS kart'),
        ('online', 'Onlayn (QR/link)'),
    ]
    GATEWAY_CHOICES = [
        ('', '—'),
        ('mock', 'Mock (dev)'),
        ('payriff', 'Payriff'),
        ('epoint', 'Epoint'),
    ]

    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='payments',
    )
    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='payments',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default='AZN')
    method = models.CharField(
        max_length=20, choices=METHOD_CHOICES, default='online'
    )
    gateway = models.CharField(
        max_length=20, choices=GATEWAY_CHOICES, blank=True, default='mock'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )

    # Gateway cavabları — kart № yoxdur
    payment_url = models.URLField(blank=True, default='')
    qr_code_url = models.URLField(blank=True, default='')
    gateway_invoice_id = models.CharField(max_length=120, blank=True, default='')
    gateway_transaction_id = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        unique=True,
        help_text='Idempotentlik: eyni webhook təkrar emal olunmasın',
    )

    paid_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True, default='')
    raw_response = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Ödəniş'
        verbose_name_plural = 'Ödənişlər'
        indexes = [
            models.Index(fields=['status', 'expires_at']),
            models.Index(fields=['order', 'status']),
        ]

    def __str__(self):
        return f'Payment #{self.pk} order={self.order_id} ({self.status})'

    def mark_paid(self, transaction_id: str, raw=None):
        if self.status == 'paid':
            return False
        self.status = 'paid'
        tid = (transaction_id or '').strip() or None
        self.gateway_transaction_id = tid
        self.paid_at = timezone.now()
        if raw is not None:
            self.raw_response = raw
        self.save(
            update_fields=[
                'status',
                'gateway_transaction_id',
                'paid_at',
                'raw_response',
                'updated_at',
            ]
        )
        return True

    def mark_failed(self, reason: str = '', raw=None):
        if self.status in ('paid', 'refunded'):
            return False
        self.status = 'failed'
        self.failure_reason = (reason or '')[:255]
        if raw is not None:
            self.raw_response = raw
        self.save(
            update_fields=[
                'status',
                'failure_reason',
                'raw_response',
                'updated_at',
            ]
        )
        return True
