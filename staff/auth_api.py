"""
Auth — admin (email+şifrə) və planşet PIN girişi.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.models import Restaurant

from .models import AccessToken, Device, StaffUser
from .permissions import (
    ADMIN_ROLES,
    can_assign_owner_role,
    home_for_role,
    report_tabs_for,
    routes_for_role,
    settings_tabs_for,
)


def _new_key() -> str:
    return secrets.token_urlsafe(32)


def _serialize_staff(staff: StaffUser) -> dict:
    email = ''
    if staff.user_id:
        email = staff.user.email or staff.user.username or ''
    return {
        'id': staff.id,
        'full_name': staff.display_name,
        'email': email,
        'initials': staff.initials,
        'role': staff.role,
        'role_label': staff.get_role_display(),
        'can_discount': staff.can_discount,
        'can_edit_menu': staff.can_edit_menu,
        'can_cancel_preparing_order': staff.can_cancel_preparing_order,
        'can_apply_discount': staff.can_apply_discount,
        'can_edit_menu_prices': staff.can_edit_menu_prices,
        'can_assign_owner': can_assign_owner_role(staff),
        'home_path': home_for_role(staff.role),
        'allowed_routes': routes_for_role(staff.role),
        'settings_tabs': settings_tabs_for(staff),
        'report_tabs': report_tabs_for(staff),
    }


def _serialize_restaurant(r: Restaurant) -> dict:
    from restaurants.subscriptions import (
        days_until_expiry,
        subscription_is_active,
    )

    active = subscription_is_active(r)
    days_left = days_until_expiry(r) if active else None
    return {
        'id': r.id,
        'name': r.name or r.slug,
        'slug': r.slug,
        'subscription_plan': r.subscription_plan or '',
        'subscription_interval': r.subscription_interval or '',
        'subscription_at': r.subscription_at.isoformat()
        if r.subscription_at
        else None,
        'subscription_expires_at': r.subscription_expires_at.isoformat()
        if r.subscription_expires_at
        else None,
        'subscription_amount': str(r.subscription_amount)
        if r.subscription_amount is not None
        else None,
        'subscription_active': active,
        'subscription_days_left': days_left,
        'needs_subscription': not active,
    }


def get_token_from_request(request) -> AccessToken | None:
    auth = request.META.get('HTTP_AUTHORIZATION', '')
    key = ''
    if auth.lower().startswith('bearer '):
        key = auth[7:].strip()
    if not key:
        key = (request.headers.get('X-Auth-Token') or '').strip()
    if not key:
        return None
    token = (
        AccessToken.objects.select_related(
            'staff', 'staff__user', 'user', 'restaurant', 'device'
        )
        .filter(key=key)
        .first()
    )
    if not token:
        return None
    if token.expires_at and token.expires_at < timezone.now():
        token.delete()
        return None
    return token


def get_device_from_request(request) -> Device | None:
    raw = (
        request.headers.get('X-Device-Token')
        or request.data.get('device_token')
        or request.query_params.get('device_token')
        or ''
    ).strip()
    if not raw:
        return None
    device = (
        Device.objects.select_related('restaurant')
        .filter(token=raw, is_active=True)
        .first()
    )
    if device:
        Device.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
    return device


def issue_token(
    *,
    kind: str,
    restaurant: Restaurant,
    user=None,
    staff=None,
    device=None,
    days: int | None = 14,
) -> AccessToken:
    expires = None
    if days is not None:
        expires = timezone.now() + timedelta(days=days)
    return AccessToken.objects.create(
        key=_new_key(),
        kind=kind,
        restaurant=restaurant,
        user=user,
        staff=staff,
        device=device,
        expires_at=expires,
    )


class AdminLoginView(APIView):
    """Sahib/menecer — e-poçt + şifrə."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        password = request.data.get('password') or ''
        remember = bool(request.data.get('remember', True))

        if not email or not password:
            return Response(
                {'detail': 'E-poçt və şifrə tələb olunur'}, status=400
            )

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            user = User.objects.filter(username__iexact=email).first()
        if not user or not user.check_password(password):
            return Response(
                {'detail': 'E-poçt və ya şifrə yanlışdır'}, status=401
            )
        if not user.is_active:
            return Response({'detail': 'Hesab deaktivdir'}, status=403)

        staff = (
            StaffUser.objects.select_related('restaurant')
            .filter(user=user, is_active=True)
            .first()
        )
        if not staff:
            return Response(
                {'detail': 'Bu hesab heç bir restoran işçisinə bağlı deyil'},
                status=403,
            )
        if staff.role not in ADMIN_ROLES and not user.is_superuser:
            return Response(
                {
                    'detail': 'Admin panel yalnız sahib/menecer üçündür. '
                    'Planşetdə PIN ilə daxil olun.'
                },
                status=403,
            )

        days = 30 if remember else 1
        token = issue_token(
            kind='admin',
            restaurant=staff.restaurant,
            user=user,
            staff=staff,
            days=days,
        )
        restaurant = _serialize_restaurant(staff.restaurant)
        home = (
            '/register'
            if restaurant['needs_subscription']
            else home_for_role(staff.role)
        )
        return Response(
            {
                'token': token.key,
                'mode': 'admin',
                'staff': _serialize_staff(staff),
                'restaurant': restaurant,
                'home_path': home,
                'needs_subscription': restaurant['needs_subscription'],
            }
        )


class RegisterView(APIView):
    """Yeni restoran sahibi qeydiyyatı."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        from datetime import time

        from django.db import transaction
        from django.utils.text import slugify

        full_name = (request.data.get('full_name') or '').strip()
        restaurant_name = (request.data.get('restaurant_name') or '').strip()
        email = (request.data.get('email') or '').strip().lower()
        password = request.data.get('password') or ''

        if not full_name or not restaurant_name or not email or not password:
            return Response(
                {'detail': 'Ad, restoran, e-poçt və şifrə tələb olunur'},
                status=400,
            )
        if len(password) < 6:
            return Response(
                {'detail': 'Şifrə ən azı 6 simvol olmalıdır'}, status=400
            )
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(
            username__iexact=email
        ).exists():
            return Response(
                {'detail': 'Bu e-poçt artıq qeydiyyatdan keçib'}, status=400
            )

        base = slugify(restaurant_name) or 'restaurant'
        slug = base
        n = 2
        while Restaurant.objects.filter(slug=slug).exists():
            slug = f'{base}-{n}'
            n += 1

        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=full_name[:30],
            )
            from django.conf import settings as dj_settings

            restaurant = Restaurant.objects.create(
                name=restaurant_name,
                slug=slug,
                opening_time=time(10, 0),
                closing_time=time(23, 0),
                qr_menu_base_url=getattr(
                    dj_settings, 'PUBLIC_MENU_BASE', 'http://127.0.0.1:5173'
                ),
            )
            staff = StaffUser.objects.create(
                restaurant=restaurant,
                user=user,
                full_name=full_name,
                role='owner',
                can_discount=True,
                can_edit_menu=True,
                can_cancel_preparing_order=True,
            )
            token = issue_token(
                kind='admin',
                restaurant=restaurant,
                user=user,
                staff=staff,
                days=30,
            )

        return Response(
            {
                'token': token.key,
                'mode': 'admin',
                'staff': _serialize_staff(staff),
                'restaurant': _serialize_restaurant(restaurant),
                'home_path': '/register',
                'needs_subscription': True,
            },
            status=201,
        )


class SubscribeView(APIView):
    """Qeydiyyatdan sonra / yeniləmə — abunə planı seçimi."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        from restaurants.subscriptions import (
            ALLOWED_INTERVALS,
            ALLOWED_PLANS,
            compute_expiry,
            price_for,
        )

        token = get_token_from_request(request)
        if not token or not token.staff:
            return Response({'detail': 'Giriş edilməyib'}, status=401)
        if token.staff.role not in ADMIN_ROLES and not (
            token.user and token.user.is_superuser
        ):
            return Response({'detail': 'İcazə yoxdur'}, status=403)

        plan = (request.data.get('plan') or '').strip().lower()
        interval = (request.data.get('interval') or 'monthly').strip().lower()
        if plan not in ALLOWED_PLANS:
            return Response({'detail': 'Yanlış plan'}, status=400)
        if interval not in ALLOWED_INTERVALS:
            return Response({'detail': 'Yanlış interval'}, status=400)

        now = timezone.now()
        restaurant = token.restaurant
        # Aktiv abunə varsa bitmə tarixindən uzat
        start = now
        if (
            restaurant.subscription_expires_at
            and restaurant.subscription_expires_at > now
        ):
            start = restaurant.subscription_expires_at

        amount = price_for(plan, interval)
        restaurant.subscription_plan = plan
        restaurant.subscription_interval = interval
        restaurant.subscription_at = now
        restaurant.subscription_expires_at = compute_expiry(
            interval=interval, from_dt=start
        )
        restaurant.subscription_amount = amount
        restaurant.save(
            update_fields=[
                'subscription_plan',
                'subscription_interval',
                'subscription_at',
                'subscription_expires_at',
                'subscription_amount',
            ]
        )

        return Response(
            {
                'restaurant': _serialize_restaurant(restaurant),
                'home_path': home_for_role(token.staff.role),
                'needs_subscription': False,
                'amount': str(amount),
                'interval': interval,
            }
        )


class DevicePairView(APIView):
    """Planşeti restoran hesabına bağla (quraşdırma kodu ilə)."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        code = (request.data.get('setup_code') or '').strip().upper()
        name = (request.data.get('device_name') or 'Planşet').strip()[:120]
        if not code:
            return Response(
                {'detail': 'Quraşdırma kodu tələb olunur'}, status=400
            )

        restaurant = Restaurant.objects.filter(
            device_setup_code__iexact=code, is_active=True
        ).first()
        if not restaurant:
            return Response(
                {'detail': 'Quraşdırma kodu yanlışdır'}, status=404
            )

        device = Device.objects.create(
            restaurant=restaurant,
            token=_new_key(),
            name=name or 'Planşet',
        )
        return Response(
            {
                'device_token': device.token,
                'device_name': device.name,
                'restaurant': _serialize_restaurant(restaurant),
            },
            status=201,
        )


class DeviceStaffListView(APIView):
    """PIN ekranı üçün aktiv işçilər (PIN göstərilmir)."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        device = get_device_from_request(request)
        if not device:
            return Response(
                {'detail': 'Cihaz bağlı deyil', 'code': 'device_required'},
                status=401,
            )
        qs = StaffUser.objects.filter(
            restaurant=device.restaurant,
            is_active=True,
        ).exclude(pin_code='').order_by('full_name')
        return Response(
            {
                'restaurant': _serialize_restaurant(device.restaurant),
                'results': [
                    {
                        'id': s.id,
                        'full_name': s.display_name,
                        'initials': s.initials,
                        'role': s.role,
                        'role_label': s.get_role_display(),
                    }
                    for s in qs
                ],
            }
        )


class PinLoginView(APIView):
    """Ortaq planşet — işçi seç + 4 rəqəmli PIN."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        device = get_device_from_request(request)
        if not device:
            return Response(
                {'detail': 'Cihaz bağlı deyil', 'code': 'device_required'},
                status=401,
            )

        staff_id = request.data.get('staff_id')
        pin = str(request.data.get('pin') or '').strip()
        if not staff_id or not pin:
            return Response(
                {'detail': 'İşçi və PIN tələb olunur'}, status=400
            )

        staff = (
            StaffUser.objects.select_related('restaurant')
            .filter(
                pk=staff_id,
                restaurant=device.restaurant,
                is_active=True,
            )
            .first()
        )
        if not staff or not staff.has_pin:
            return Response({'detail': 'İşçi tapılmadı'}, status=404)

        if not staff.check_pin(pin):
            return Response({'detail': 'Yanlış PIN'}, status=401)

        # Köhnə plain PIN-i hash-ə çevir
        try:
            from django.contrib.auth.hashers import identify_hasher

            identify_hasher(staff.pin_code)
        except Exception:
            staff.set_pin(pin)
            staff.save(update_fields=['pin_code'])

        # Əvvəlki staff token-ləri bu cihaz üçün sil (tək aktiv işçi)
        AccessToken.objects.filter(device=device, kind='staff').delete()

        token = issue_token(
            kind='staff',
            restaurant=device.restaurant,
            staff=staff,
            device=device,
            days=1,  # növbəlik — qısa ömür
        )

        # Django session (əlavə audit izi)
        try:
            request.session['active_staff_id'] = staff.id
            request.session['device_id'] = device.id
            request.session['restaurant_id'] = device.restaurant_id
        except Exception:
            pass

        return Response(
            {
                'token': token.key,
                'mode': 'pin',
                'staff': _serialize_staff(staff),
                'restaurant': _serialize_restaurant(device.restaurant),
                'home_path': home_for_role(staff.role),
            }
        )


class MeView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        token = get_token_from_request(request)
        if not token:
            return Response({'detail': 'Giriş edilməyib'}, status=401)
        staff = token.staff
        if not staff:
            return Response({'detail': 'İşçi tapılmadı'}, status=401)
        restaurant = _serialize_restaurant(token.restaurant)
        return Response(
            {
                'mode': token.kind,
                'staff': _serialize_staff(staff),
                'restaurant': restaurant,
                'home_path': (
                    '/register'
                    if restaurant['needs_subscription']
                    else home_for_role(staff.role)
                ),
                'needs_subscription': restaurant['needs_subscription'],
                'device_bound': bool(token.device_id),
            }
        )


MOBILE_ROLES = ('courier', 'waiter', 'kitchen', 'cashier')


class MobileStaffListView(APIView):
    """Mobil tətbiq — PIN girişi üçün ofisiant/kuryer/… siyahısı (cihaz cütləşməsiz)."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        slug = (request.query_params.get('slug') or 'surfues-resto').strip()
        restaurant = Restaurant.objects.filter(slug=slug, is_active=True).first()
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        rows = (
            StaffUser.objects.filter(
                restaurant=restaurant,
                is_active=True,
                role__in=MOBILE_ROLES,
            )
            .exclude(pin_code='')
            .order_by('role', 'full_name')
        )
        return Response(
            {
                'restaurant': _serialize_restaurant(restaurant),
                'staff': [
                    {
                        'id': s.id,
                        'full_name': s.display_name,
                        'initials': s.initials,
                        'role': s.role,
                        'role_label': s.get_role_display(),
                    }
                    for s in rows
                ],
            }
        )


class MobileLoginView(APIView):
    """Mobil tətbiq — işçi + PIN; rol cavabda qaytarılır."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        slug = (request.data.get('slug') or 'surfues-resto').strip()
        pin = str(request.data.get('pin') or '').strip()
        staff_id = request.data.get('staff_id')

        restaurant = Restaurant.objects.filter(slug=slug, is_active=True).first()
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        if not staff_id or not pin:
            return Response({'detail': 'İşçi və PIN tələb olunur'}, status=400)

        staff = (
            StaffUser.objects.select_related('restaurant', 'user')
            .filter(
                pk=staff_id,
                restaurant=restaurant,
                is_active=True,
                role__in=MOBILE_ROLES,
            )
            .first()
        )
        if not staff or not staff.has_pin:
            return Response({'detail': 'İşçi tapılmadı'}, status=404)
        if not staff.check_pin(pin):
            return Response({'detail': 'Yanlış PIN'}, status=401)

        try:
            from django.contrib.auth.hashers import identify_hasher

            identify_hasher(staff.pin_code)
        except Exception:
            staff.set_pin(pin)
            staff.save(update_fields=['pin_code'])

        if not staff.user_id:
            username = f'staff_{restaurant.slug}_{staff.id}'
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={'first_name': staff.display_name[:30]},
            )
            staff.user = user
            staff.save(update_fields=['user'])

        token = issue_token(
            kind='staff',
            restaurant=restaurant,
            staff=staff,
            user=staff.user,
            days=30,
        )

        courier_payload = None
        if staff.role == 'courier':
            from delivery.services import ensure_courier_profile

            courier = ensure_courier_profile(staff)
            if courier:
                courier_payload = {
                    'id': courier.id,
                    'full_name': courier.display_name,
                    'phone': courier.phone,
                    'is_available': courier.is_available,
                }

        return Response(
            {
                'token': token.key,
                'staff': _serialize_staff(staff),
                'restaurant': _serialize_restaurant(restaurant),
                'courier': courier_payload,
            }
        )


class LogoutView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        token = get_token_from_request(request)
        if token:
            token.delete()
        try:
            request.session.pop('active_staff_id', None)
        except Exception:
            pass
        return Response({'ok': True})


class SwitchStaffView(APIView):
    """PIN rejimində işçi dəyiş (token-i sil, PIN ekranına qayıt)."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        token = get_token_from_request(request)
        if token and token.kind == 'staff':
            token.delete()
        try:
            request.session.pop('active_staff_id', None)
        except Exception:
            pass
        return Response({'ok': True, 'next': '/login'})


class DeleteAccountView(APIView):
    """Sahib hesabı və restoranı silir."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        from django.db import transaction

        token = get_token_from_request(request)
        if not token or not token.staff:
            return Response({'detail': 'Giriş edilməyib'}, status=401)

        staff = token.staff
        if staff.role != 'owner' and not (
            token.user and token.user.is_superuser
        ):
            return Response(
                {'detail': 'Hesabı yalnız sahib silə bilər'}, status=403
            )

        confirm = (request.data.get('confirm') or '').strip()
        if confirm != 'SIL':
            return Response(
                {'detail': 'Təsdiq üçün SIL yazın'}, status=400
            )

        restaurant = token.restaurant
        user_ids = list(
            StaffUser.objects.filter(restaurant=restaurant)
            .exclude(user_id=None)
            .values_list('user_id', flat=True)
        )

        with transaction.atomic():
            AccessToken.objects.filter(restaurant=restaurant).delete()
            restaurant.delete()
            if user_ids:
                User.objects.filter(pk__in=user_ids).delete()

        return Response({'ok': True})
