from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password, identify_hasher
from django.db import models


class StaffUser(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Sahib'),
        ('manager', 'Menecer'),
        ('waiter', 'Ofisiant'),
        ('kitchen', 'Mətbəx'),
        ('cashier', 'Kassir'),
        ('courier', 'Kuryer'),
        ('warehouse', 'Anbar'),
    ]

    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='staff',
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='staff_profile',
        null=True,
        blank=True,
    )
    full_name = models.CharField(max_length=120, blank=True, default='')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    # Hash saxlanır (make_password) — heç vaxt açıq mətn
    pin_code = models.CharField(max_length=128, blank=True, default='')
    is_active = models.BooleanField(default=True)
    # Rol default-unu override — İşçi idarəetməsində checkbox (UI v2 tam)
    can_discount = models.BooleanField(
        default=False,
        help_text='Endirim tətbiq edə bilər (rol defaultundan əlavə)',
    )
    can_edit_menu = models.BooleanField(
        default=False,
        help_text='Menyu/qiymət redaktə (rol defaultundan əlavə)',
    )
    can_cancel_preparing_order = models.BooleanField(
        default=False,
        help_text='Hazırlanan sifarişi ləğv edə bilər (əks halda menecer)',
    )

    class Meta:
        verbose_name = 'İşçi'
        verbose_name_plural = 'İşçilər'

    def __str__(self):
        label = self.full_name or (
            self.user.get_username() if self.user_id else '?'
        )
        return f'{label} — {self.get_role_display()} ({self.restaurant})'

    def set_pin(self, raw_pin: str) -> None:
        self.pin_code = make_password(str(raw_pin))

    def check_pin(self, raw_pin: str) -> bool:
        if not self.pin_code or raw_pin is None:
            return False
        try:
            identify_hasher(self.pin_code)
            return check_password(str(raw_pin), self.pin_code)
        except Exception:
            # Köhnə plain-text PIN (miqrasiya keçidi)
            return str(self.pin_code) == str(raw_pin)

    @property
    def has_pin(self) -> bool:
        return bool(self.pin_code)

    @property
    def can_apply_discount(self) -> bool:
        from .permissions import can_apply_discount

        return can_apply_discount(self)

    @property
    def can_edit_menu_prices(self) -> bool:
        from .permissions import can_edit_menu_prices

        return can_edit_menu_prices(self)

    @property
    def display_name(self) -> str:
        if self.full_name.strip():
            return self.full_name.strip()
        if self.user_id:
            return self.user.get_full_name() or self.user.get_username()
        return 'İşçi'

    @property
    def initials(self) -> str:
        parts = self.display_name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return (self.display_name[:2] or '?').upper()


class Device(models.Model):
    """Planşet/cihaz — restoran hesabına bağlı."""

    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='devices',
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=120, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Cihaz'
        verbose_name_plural = 'Cihazlar'

    def __str__(self):
        return f'{self.name or "Cihaz"} · {self.restaurant.slug}'


class AccessToken(models.Model):
    KIND_CHOICES = [
        ('admin', 'Admin'),
        ('staff', 'PIN işçi'),
    ]

    key = models.CharField(max_length=64, unique=True, db_index=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    restaurant = models.ForeignKey(
        'restaurants.Restaurant',
        on_delete=models.CASCADE,
        related_name='access_tokens',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='surfues_tokens',
    )
    staff = models.ForeignKey(
        StaffUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='access_tokens',
    )
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='access_tokens',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.kind}:{self.key[:8]}…'
