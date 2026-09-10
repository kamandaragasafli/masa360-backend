from rest_framework import serializers

from .models import KitchenPrinter, Restaurant


class RestaurantSerializer(serializers.ModelSerializer):
    kitchen_mode_label = serializers.CharField(
        source='get_kitchen_mode_display', read_only=True
    )
    logo_url = serializers.SerializerMethodField()
    payment_api_key_set = serializers.SerializerMethodField()
    shop_url = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = (
            'id',
            'name',
            'slug',
            'address',
            'phone',
            'logo',
            'logo_url',
            'is_active',
            'opening_time',
            'closing_time',
            'opening_hours',
            'currency',
            'vat_percent',
            'service_charge_percent',
            'service_charge_enabled',
            'kitchen_mode',
            'kitchen_mode_label',
            'qr_menu_base_url',
            'qr_design',
            'qr_scan_mode',
            'qr_enabled',
            'accept_cash',
            'accept_card',
            'accept_online',
            'payment_gateway',
            'payment_api_key',
            'payment_api_key_set',
            'notify_push_waiter',
            'notify_push_courier',
            'notify_push_manager',
            'notify_expiry_days',
            'notify_kitchen_sound',
            'notify_sound_waiter',
            'notify_sound_manager',
            'notify_daily_summary_hour',
            'notify_stock_threshold',
            'delivery_enabled',
            'delivery_radius_km',
            'delivery_fee_type',
            'delivery_fee_amount',
            'delivery_base_fee',
            'delivery_per_km_fee',
            'lat',
            'lng',
            'panel_language',
            'customer_menu_multilang',
            'device_setup_code',
            'custom_domain',
            'storefront_enabled',
            'shop_url',
        )
        extra_kwargs = {
            'payment_api_key': {'write_only': True, 'required': False},
            'logo': {'write_only': True, 'required': False},
            'slug': {'read_only': True},
            'device_setup_code': {'read_only': True},
            'shop_url': {'read_only': True},
        }

    def get_shop_url(self, obj):
        return obj.public_shop_url()

    def validate_custom_domain(self, value):
        from restaurants.domains import is_platform_host, normalize_domain

        raw = (value or '').strip()
        if not raw:
            return ''
        d = normalize_domain(raw)
        if not d:
            raise serializers.ValidationError('Domen formatı yanlışdır')
        if is_platform_host(d):
            raise serializers.ValidationError(
                'Bu domen platformaya aiddir, istifadə edilə bilməz'
            )
        qs = Restaurant.objects.filter(custom_domain=d)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Bu domen artıq bağlıdır')
        return d

    def get_logo_url(self, obj):
        if not obj.logo:
            return ''
        request = self.context.get('request')
        url = obj.logo.url
        if request:
            return request.build_absolute_uri(url)
        return url

    def get_payment_api_key_set(self, obj):
        return bool(obj.payment_api_key)

    def update(self, instance, validated_data):
        # Boş API açarı göndərilibsə — əvvəlkini saxla
        if 'payment_api_key' in validated_data and not validated_data['payment_api_key']:
            validated_data.pop('payment_api_key')
        if 'custom_domain' in validated_data and not validated_data['custom_domain']:
            validated_data['custom_domain'] = None
        return super().update(instance, validated_data)


class KitchenPrinterSerializer(serializers.ModelSerializer):
    class Meta:
        model = KitchenPrinter
        fields = (
            'id',
            'name',
            'ip_address',
            'port',
            'is_active',
            'created_at',
        )
        read_only_fields = ('created_at',)
