"""Kuryer REST API — auth, mövcudluq, təklif, çatdırma, qazanc."""

from __future__ import annotations

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.models import Restaurant
from staff.auth_api import get_token_from_request, issue_token
from staff.models import StaffUser

from .models import Courier, DeliveryAssignment
from .services import (
    accept_assignment,
    assign_courier,
    earnings_summary,
    ensure_courier_profile,
    generate_delivery_otp,
    is_delivery_order,
    serialize_assignment,
    serialize_offer,
)


def _courier_from_request(request) -> Courier | None:
    token = get_token_from_request(request)
    if not token or not token.staff_id:
        return None
    return ensure_courier_profile(token.staff)


def _require_courier(request):
    courier = _courier_from_request(request)
    if not courier:
        return None, Response({'detail': 'Kuryer girişi tələb olunur'}, status=401)
    return courier, None


class CourierLoginView(APIView):
    """Mobil kuryer — restoran slug + işçi + PIN (cihaz cütləşməsiz)."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        slug = (request.data.get('slug') or 'surfues-resto').strip()
        pin = str(request.data.get('pin') or '').strip()
        staff_id = request.data.get('staff_id')
        phone = (request.data.get('phone') or '').strip()

        restaurant = Restaurant.objects.filter(slug=slug, is_active=True).first()
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        qs = StaffUser.objects.filter(
            restaurant=restaurant, role='courier', is_active=True
        )
        staff = None
        if staff_id:
            staff = qs.filter(pk=staff_id).first()
        elif phone:
            staff = (
                Courier.objects.filter(
                    restaurant=restaurant, phone=phone, staff__isnull=False
                )
                .select_related('staff')
                .first()
            )
            staff = staff.staff if staff else None
            if not staff:
                # phone staff.full_name fallback yox — yalnız Courier.phone
                pass
        else:
            # Demo rahatlığı: tək kuryer varsa onu seç
            if qs.count() == 1:
                staff = qs.first()

        if not staff or not pin:
            return Response(
                {'detail': 'Kuryer və PIN tələb olunur'}, status=400
            )
        if not staff.check_pin(pin):
            return Response({'detail': 'Yanlış PIN'}, status=401)

        if not staff.user_id:
            from django.contrib.auth.models import User

            username = f'courier_{restaurant.slug}_{staff.id}'
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={'first_name': staff.display_name[:30]},
            )
            staff.user = user
            staff.save(update_fields=['user'])

        # Yalnız öz restoranının kuryeri
        if staff.restaurant_id != restaurant.id:
            return Response({'detail': 'Bu restoran üçün kuryer deyil'}, status=403)

        courier = ensure_courier_profile(staff)
        if phone and courier and not courier.phone:
            courier.phone = phone
            courier.save(update_fields=['phone'])

        token = issue_token(
            kind='staff',
            restaurant=restaurant,
            staff=staff,
            user=staff.user,
            days=30,
        )
        return Response(
            {
                'token': token.key,
                'courier': {
                    'id': courier.id,
                    'full_name': courier.display_name,
                    'phone': courier.phone,
                    'is_available': courier.is_available,
                },
                'restaurant': {
                    'id': restaurant.id,
                    'name': restaurant.name or restaurant.slug,
                    'slug': restaurant.slug,
                },
            }
        )


class CourierStaffListView(APIView):
    """Login ekranı üçün kuryer siyahısı."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        slug = (request.query_params.get('slug') or 'surfues-resto').strip()
        restaurant = Restaurant.objects.filter(slug=slug, is_active=True).first()
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        rows = StaffUser.objects.filter(
            restaurant=restaurant, role='courier', is_active=True
        ).order_by('full_name')
        return Response(
            {
                'restaurant': {
                    'id': restaurant.id,
                    'name': restaurant.name or restaurant.slug,
                    'slug': restaurant.slug,
                },
                'staff': [
                    {
                        'id': s.id,
                        'full_name': s.display_name,
                        'initials': s.initials,
                    }
                    for s in rows
                ],
            }
        )


class CourierMeView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        courier, err = _require_courier(request)
        if err:
            return err
        today = earnings_summary(courier, preset='today')
        active = (
            DeliveryAssignment.objects.filter(
                courier=courier,
                status__in=('accepted', 'picked_up'),
            )
            .select_related('order', 'restaurant')
            .prefetch_related('order__items__menu_item')
            .order_by('-accepted_at')
            .first()
        )
        pending = (
            DeliveryAssignment.objects.filter(
                restaurant=courier.restaurant,
                status='offered',
            )
            .select_related('order', 'restaurant')
            .prefetch_related('order__items__menu_item')
            .order_by('-offered_at')
            .first()
            if courier.is_available
            else None
        )
        return Response(
            {
                'courier': {
                    'id': courier.id,
                    'full_name': courier.display_name,
                    'phone': courier.phone,
                    'is_available': courier.is_available,
                    'current_lat': courier.current_lat,
                    'current_lng': courier.current_lng,
                },
                'today_earnings': today['total_amount'],
                'today_deliveries': today['total_deliveries'],
                'active_assignment': (
                    serialize_assignment(active) if active else None
                ),
                'pending_offer': serialize_offer(pending) if pending else None,
            }
        )


class CourierAvailabilityView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        courier, err = _require_courier(request)
        if err:
            return err
        available = bool(request.data.get('is_available'))
        courier.is_available = available
        courier.save(update_fields=['is_available'])
        return Response({'is_available': courier.is_available})


class CourierLocationView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        courier, err = _require_courier(request)
        if err:
            return err
        try:
            lat = float(request.data.get('lat'))
            lng = float(request.data.get('lng'))
        except (TypeError, ValueError):
            return Response({'detail': 'lat/lng tələb olunur'}, status=400)
        courier.current_lat = lat
        courier.current_lng = lng
        courier.last_location_update = timezone.now()
        courier.save(
            update_fields=[
                'current_lat',
                'current_lng',
                'last_location_update',
            ]
        )
        # Aktiv sifariş izləməsinə ötürmə (REST fallback)
        active = DeliveryAssignment.objects.filter(
            courier=courier, status__in=('accepted', 'picked_up')
        ).first()
        if active:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            from .services import tracking_group

            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(
                    tracking_group(active.order_id),
                    {
                        'type': 'location.update',
                        'lat': lat,
                        'lng': lng,
                        'order_id': active.order_id,
                    },
                )
        return Response({'ok': True})


class OfferAcceptView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, pk):
        courier, err = _require_courier(request)
        if err:
            return err
        assignment = DeliveryAssignment.objects.filter(pk=pk).first()
        if not assignment:
            return Response({'detail': 'Təklif tapılmadı'}, status=404)
        a, fail = accept_assignment(assignment, courier)
        if fail:
            return Response({'detail': fail, 'code': 'taken'}, status=409)
        a = (
            DeliveryAssignment.objects.filter(pk=a.pk)
            .select_related('order', 'restaurant')
            .prefetch_related('order__items__menu_item')
            .first()
        )
        return Response(serialize_assignment(a))


class OfferRejectView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, pk):
        courier, err = _require_courier(request)
        if err:
            return err
        # Broadcast-də rədd = bu kuryer üçün UI bağlanır; digərləri gözləyir
        return Response({'ok': True, 'assignment_id': pk})


class AssignmentPickupView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, pk):
        courier, err = _require_courier(request)
        if err:
            return err
        a = (
            DeliveryAssignment.objects.filter(pk=pk, courier=courier)
            .select_related('order', 'restaurant')
            .prefetch_related('order__items__menu_item')
            .first()
        )
        if not a:
            return Response({'detail': 'Tapşırıq tapılmadı'}, status=404)
        if a.status != 'accepted':
            return Response({'detail': 'Status uyğun deyil'}, status=400)
        a.status = 'picked_up'
        a.picked_up_at = timezone.now()
        a.save(update_fields=['status', 'picked_up_at'])
        if a.confirmation_method == 'otp' and not a.confirmation_otp:
            generate_delivery_otp(a)
            a.refresh_from_db()
        return Response(serialize_assignment(a))


class AssignmentDeliverView(APIView):
    """OTP və ya foto ilə çatdırma təsdiqi."""

    authentication_classes = []
    permission_classes = []

    def post(self, request, pk):
        courier, err = _require_courier(request)
        if err:
            return err
        a = DeliveryAssignment.objects.filter(pk=pk, courier=courier).first()
        if not a:
            return Response({'detail': 'Tapşırıq tapılmadı'}, status=404)
        if a.status != 'picked_up':
            return Response(
                {'detail': 'Əvvəl sifarişi götürün'}, status=400
            )

        method = a.confirmation_method
        if method == 'otp':
            otp = str(request.data.get('otp') or '').strip()
            if not a.confirmation_otp:
                generate_delivery_otp(a)
                a.refresh_from_db()
            if otp != a.confirmation_otp:
                return Response({'detail': 'Yanlış kod'}, status=400)
        else:
            photo = request.FILES.get('photo')
            if not photo:
                return Response({'detail': 'Foto tələb olunur'}, status=400)
            a.confirmation_photo = photo

        a.status = 'delivered'
        a.delivered_at = timezone.now()
        a.save()
        order = a.order
        order.status = 'completed'
        order.apply_status_timestamp('completed')
        order.save(update_fields=['status', 'completed_at', 'updated_at'])
        return Response(serialize_assignment(a))


class EarningsView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        courier, err = _require_courier(request)
        if err:
            return err
        preset = request.query_params.get('preset') or 'today'
        if preset not in ('today', 'week'):
            preset = 'today'
        return Response(earnings_summary(courier, preset=preset))


class DemoOfferView(APIView):
    """Dev: restoranın öz kuryerlərinə test təyinatı."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        courier, err = _require_courier(request)
        if err:
            return err
        from orders.models import Order

        restaurant = courier.restaurant
        if not restaurant.delivery_enabled:
            restaurant.delivery_enabled = True
            if not restaurant.delivery_fee_amount:
                restaurant.delivery_fee_amount = 18
            restaurant.save(
                update_fields=['delivery_enabled', 'delivery_fee_amount']
            )

        # Demo üçün bu kuryeri aktiv et
        if not courier.is_available:
            courier.is_available = True
            courier.save(update_fields=['is_available'])

        order = Order.objects.create(
            restaurant=restaurant,
            table=None,
            source='mobile_app',
            order_type='delivery',
            status='ready',
            total_amount=25,
            notes='28 May küç. 14, mən. 12',
            guest_phone='+994501234567',
            delivery_address='28 May küç. 14, mən. 12',
            customer_phone='+994501234567',
            delivery_lat=40.3798,
            delivery_lng=49.8465,
            delivery_fee=18,
        )

        assignment = assign_courier(
            order,
            dropoff_address=order.notes,
            customer_phone=order.guest_phone,
        )
        if not assignment:
            return Response({'detail': 'Yaradıla bilmədi'}, status=400)
        return Response(serialize_assignment(assignment))
