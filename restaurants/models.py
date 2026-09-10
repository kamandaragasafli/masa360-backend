from django.db import models
from django.utils.text import slugify


DEFAULT_OPENING_HOURS = [
    {'day': 0, 'label': 'Bazar ertəsi', 'closed': False, 'open': '10:00', 'close': '23:00'},
    {'day': 1, 'label': 'Çərşənbə axşamı', 'closed': False, 'open': '10:00', 'close': '23:00'},
    {'day': 2, 'label': 'Çərşənbə', 'closed': False, 'open': '10:00', 'close': '23:00'},
    {'day': 3, 'label': 'Cümə axşamı', 'closed': False, 'open': '10:00', 'close': '23:00'},
    {'day': 4, 'label': 'Cümə', 'closed': False, 'open': '10:00', 'close': '23:00'},
    {'day': 5, 'label': 'Şənbə', 'closed': False, 'open': '11:00', 'close': '00:00'},
    {'day': 6, 'label': 'Bazar', 'closed': False, 'open': '11:00', 'close': '00:00'},
]


class Restaurant(models.Model):
    KITCHEN_MODE_CHOICES = [
        ('printer', 'Termal printer (KOT)'),
        ('tablet', 'Planşet KDS'),
        ('both', 'Hər ikisi'),
    ]
    QR_DESIGN_CHOICES = [
        ('simple', 'Sadə QR'),
        ('branded', 'Loqolu / çərçivəli'),
    ]
    QR_SCAN_CHOICES = [
        ('menu_first', 'Əvvəl menyu, sonra sifariş'),
        ('order_direct', 'Birbaşa sifariş rejimi'),
    ]
    CURRENCY_CHOICES = [
        ('AZN', 'AZN (₼)'),
        ('USD', 'USD ($)'),
        ('EUR', 'EUR (€)'),
        ('TRY', 'TRY (₺)'),
    ]
    LANG_CHOICES = [
        ('az', 'Azərbaycanca'),
        ('ru', 'Русский'),
        ('en', 'English'),
    ]
    DELIVERY_FEE_CHOICES = [
        ('fixed', 'Sabit haqq'),
        ('distance', 'Məsafəyə görə'),
    ]

    name = models.CharField(max_length=255, blank=True, default='')
    slug = models.SlugField(unique=True)
    address = models.CharField(max_length=500, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    logo = models.ImageField(upload_to='restaurant_logos/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    opening_time = models.TimeField()
    closing_time = models.TimeField()
    opening_hours = models.JSONField(default=list, blank=True)

    currency = models.CharField(max_length=8, choices=CURRENCY_CHOICES, default='AZN')
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    service_charge_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    service_charge_enabled = models.BooleanField(default=False)

    kitchen_mode = models.CharField(
        max_length=20,
        choices=KITCHEN_MODE_CHOICES,
        default='both',
    )

    # Ağ label müştəri saytı (thedöner.az) — müştəri surfua yox, restoranı tapır
    custom_domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text='Öz domen: thedoner.az (www olmadan)',
    )
    storefront_enabled = models.BooleanField(
        default=True,
        help_text='Öz domen / slug ilə onlayn sifariş saytı açıqdır',
    )

    # QR
    qr_menu_base_url = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Müştəri menyusu bazası (LAN: http://192.168.x.x:5173)',
    )
    qr_design = models.CharField(
        max_length=20, choices=QR_DESIGN_CHOICES, default='branded'
    )
    qr_scan_mode = models.CharField(
        max_length=20, choices=QR_SCAN_CHOICES, default='menu_first'
    )
    qr_enabled = models.BooleanField(default=True)

    # Ödəniş
    accept_cash = models.BooleanField(default=True)
    accept_card = models.BooleanField(default=True)
    accept_online = models.BooleanField(default=False)
    payment_gateway = models.CharField(max_length=50, blank=True, default='')
    payment_api_key = models.CharField(max_length=255, blank=True, default='')

    # Bildiriş
    notify_push_waiter = models.BooleanField(default=True)
    notify_push_courier = models.BooleanField(default=False)
    notify_push_manager = models.BooleanField(default=True)
    notify_expiry_days = models.PositiveIntegerField(default=7)
    notify_kitchen_sound = models.BooleanField(default=True)
    notify_sound_waiter = models.BooleanField(default=True)
    notify_sound_manager = models.BooleanField(default=False)
    notify_daily_summary_hour = models.PositiveSmallIntegerField(
        default=23,
        help_text='Gündəlik xülasə saatı (0–23)',
    )
    notify_stock_threshold = models.PositiveIntegerField(
        default=5,
        help_text='Kritik stok həddi (ədəd)',
    )

    # Çatdırılma
    delivery_enabled = models.BooleanField(default=False)
    delivery_radius_km = models.DecimalField(
        max_digits=6, decimal_places=2, default=5,
        help_text='Max çatdırılma radiusu (km)',
    )
    delivery_fee_type = models.CharField(
        max_length=20, choices=DELIVERY_FEE_CHOICES, default='fixed'
    )
    delivery_fee_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=3,
        help_text='Sabit haqq (fee_type=fixed)',
    )
    delivery_base_fee = models.DecimalField(
        max_digits=8, decimal_places=2, default=2,
        help_text='Baza haqq (məsafə tipində)',
    )
    delivery_per_km_fee = models.DecimalField(
        max_digits=8, decimal_places=2, default=0.5,
        help_text='Hər km üçün haqq',
    )
    lat = models.FloatField(
        null=True, blank=True, help_text='Restoran koordinatı (Mapbox)'
    )
    lng = models.FloatField(
        null=True, blank=True, help_text='Restoran koordinatı (Mapbox)'
    )

    # Dil
    panel_language = models.CharField(
        max_length=5, choices=LANG_CHOICES, default='az'
    )
    customer_menu_multilang = models.BooleanField(default=False)

    # Planşet bağlama — bir dəfəlik/dövri quraşdırma kodu
    device_setup_code = models.CharField(
        max_length=16,
        blank=True,
        default='',
        help_text='Planşeti restoran hesabına bağlamaq üçün kod',
    )

    # Abunə
    PLAN_CHOICES = [
        ('start', 'Başlanğıc'),
        ('pro', 'Pro'),
        ('net', 'Şəbəkə'),
    ]
    INTERVAL_CHOICES = [
        ('monthly', 'Aylıq'),
        ('yearly', 'Illik'),
    ]
    subscription_plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        blank=True,
        default='',
    )
    subscription_interval = models.CharField(
        max_length=20,
        choices=INTERVAL_CHOICES,
        blank=True,
        default='',
    )
    subscription_at = models.DateTimeField(null=True, blank=True)
    subscription_expires_at = models.DateTimeField(null=True, blank=True)
    subscription_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Restoran'
        verbose_name_plural = 'Restoranlar'

    def __str__(self):
        return self.name or self.slug

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) or 'restaurant'
        if not self.opening_hours:
            self.opening_hours = DEFAULT_OPENING_HOURS
        if not self.device_setup_code:
            import secrets
            import string

            alphabet = string.ascii_uppercase + string.digits
            self.device_setup_code = 'SURF-' + ''.join(
                secrets.choice(alphabet) for _ in range(4)
            )
        # unique domain — boş = NULL
        raw_domain = (self.custom_domain or '').strip()
        if not raw_domain:
            self.custom_domain = None
        else:
            from restaurants.domains import normalize_domain

            self.custom_domain = normalize_domain(raw_domain) or None
        super().save(*args, **kwargs)

    @property
    def uses_printer(self):
        return self.kitchen_mode in ('printer', 'both')

    @property
    def uses_tablet(self):
        return self.kitchen_mode in ('tablet', 'both')

    def table_menu_url(self, table_number: str) -> str:
        from django.conf import settings

        from restaurants.domains import normalize_domain

        domain = normalize_domain(self.custom_domain or '')
        if domain:
            # Öz domen — slug URL-də lazım deyil
            return f'https://{domain}/masa-{table_number}'

        def _is_local_base(url: str) -> bool:
            host = (
                url.replace('https://', '')
                .replace('http://', '')
                .split('/')[0]
                .split(':')[0]
                .lower()
            )
            return (
                host in ('localhost', '127.0.0.1', '0.0.0.0')
                or host.startswith('192.168.')
                or host.startswith('10.')
                or host.startswith('172.')
            )

        base = (self.qr_menu_base_url or '').strip().rstrip('/')
        if not base or not _is_local_base(base):
            base = getattr(
                settings, 'PUBLIC_MENU_BASE', 'http://127.0.0.1:5173'
            ).rstrip('/')
        return f'{base}/{self.slug}/masa-{table_number}'

    def public_shop_url(self) -> str:
        from restaurants.domains import normalize_domain, storefront_base_url

        domain = normalize_domain(self.custom_domain or '')
        if domain:
            return f'https://{domain}'
        base = storefront_base_url(self)
        return f'{base}/{self.slug}'


class KitchenPrinter(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='printers',
    )
    name = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField()
    port = models.PositiveIntegerField(default=9100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Mətbəx printeri'
        verbose_name_plural = 'Mətbəx printerləri'
        unique_together = ('restaurant', 'name')

    def __str__(self):
        return f'{self.name} ({self.ip_address}:{self.port})'
