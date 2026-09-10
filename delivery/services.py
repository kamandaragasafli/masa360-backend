"""
Restoran öz kuryeri — təyinat məntiqi.

0 boş → menecerə bildiriş (pending/failed)
1 boş → birbaşa təyin (accepted), təklif yox
2+ boş → 12s broadcast təklif, ilk qəbul edən alır
"""

from __future__ import annotations

import logging
import random
import threading
from datetime import timedelta
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Courier, DeliveryAssignment

logger = logging.getLogger(__name__)

OFFER_SECONDS = 12


def courier_group(courier_id: int) -> str:
    return f'courier_{courier_id}'


def tracking_group(order_id: int) -> str:
    return f'order_tracking_{order_id}'


def is_delivery_order(order) -> bool:
    """Çatdırılma sifarişi — order_type='delivery'."""
    if getattr(order, 'order_type', None) == 'delivery':
        return True
    # Köhnə qeydlər / demo
    restaurant = order.restaurant
    if not restaurant.delivery_enabled:
        return False
    if order.table_id:
        return False
    return order.source in ('mobile_app', 'online')


def generate_delivery_otp(assignment: DeliveryAssignment) -> str:
    otp = f'{random.randint(1000, 9999)}'
    assignment.confirmation_otp = otp
    assignment.save(update_fields=['confirmation_otp'])
    phone = assignment.customer_phone or getattr(
        assignment.order, 'guest_phone', ''
    )
    logger.info(
        'Delivery OTP order=%s phone=%s otp=%s',
        assignment.order_id,
        phone,
        otp,
    )
    return otp


def _order_line_items(assignment: DeliveryAssignment) -> list[dict]:
    order = getattr(assignment, 'order', None)
    if order is None:
        return []
    lines = []
    qs = order.items.all()
    # prefetch varsa artıq yüklənib
    for line in qs:
        name = ''
        if getattr(line, 'menu_item_id', None) and line.menu_item:
            name = line.menu_item.name
        lines.append(
            {
                'name': name or 'Məhsul',
                'quantity': line.quantity,
                'note': (line.special_instructions or '')[:120],
            }
        )
    return lines


def serialize_offer(assignment: DeliveryAssignment) -> dict:
    restaurant = assignment.restaurant
    expires = assignment.offer_expires_at
    remaining = 0
    if expires:
        remaining = max(0, int((expires - timezone.now()).total_seconds()))
    return {
        'id': assignment.id,
        'order_id': assignment.order_id,
        'status': assignment.status,
        'restaurant_name': restaurant.name or restaurant.slug,
        'delivery_fee': f'{Decimal(str(assignment.delivery_fee)).quantize(Decimal("0.01")):.2f}',
        'pickup_address': assignment.pickup_address,
        'dropoff_address': assignment.dropoff_address,
        'customer_phone': assignment.customer_phone,
        'customer_name': assignment.customer_name,
        'distance_km': (
            str(assignment.distance_km)
            if assignment.distance_km is not None
            else None
        ),
        'eta_minutes': assignment.eta_minutes,
        'offer_seconds_left': remaining,
        'offer_expires_at': expires.isoformat() if expires else None,
        'pickup_lat': assignment.pickup_lat,
        'pickup_lng': assignment.pickup_lng,
        'dropoff_lat': assignment.dropoff_lat,
        'dropoff_lng': assignment.dropoff_lng,
        'confirmation_method': assignment.confirmation_method,
        'auto_assigned': assignment.status == 'accepted'
        and assignment.offered_at is None,
        'items': _order_line_items(assignment),
    }


def serialize_assignment(assignment: DeliveryAssignment) -> dict:
    data = serialize_offer(assignment)
    data.update(
        {
            'accepted_at': assignment.accepted_at.isoformat()
            if assignment.accepted_at
            else None,
            'picked_up_at': assignment.picked_up_at.isoformat()
            if assignment.picked_up_at
            else None,
            'delivered_at': assignment.delivered_at.isoformat()
            if assignment.delivered_at
            else None,
            'has_otp': bool(assignment.confirmation_otp),
            'confirmation_photo_url': (
                assignment.confirmation_photo.url
                if assignment.confirmation_photo
                else None
            ),
        }
    )
    from django.conf import settings

    if settings.DEBUG and assignment.confirmation_otp:
        data['debug_otp'] = assignment.confirmation_otp
    return data


def _broadcast_to_couriers(courier_ids: list[int], event: str, payload: dict):
    layer = get_channel_layer()
    if layer is None:
        return
    for cid in courier_ids:
        async_to_sync(layer.group_send)(
            courier_group(cid),
            {'type': 'courier.event', 'event': event, 'payload': payload},
        )


def _set_order_delivering(order):
    if order.status in ('ready', 'received', 'preparing', 'delivering'):
        if order.status != 'delivering':
            order.status = 'delivering'
            order.save(update_fields=['status', 'updated_at'])


def _notify_manager(restaurant, order, *, title: str, message: str):
    try:
        from notifications.services import create_notification

        create_notification(
            restaurant=restaurant,
            type='order_ready',
            title=title,
            message=message,
            recipient_role='manager',
            link='/board',
            related_order=order,
        )
    except Exception:
        logger.exception('manager notify failed')


def _base_assignment_fields(order, *, dropoff_address='', customer_phone=''):
    restaurant = order.restaurant
    fee = Decimal(
        order.delivery_fee
        if getattr(order, 'delivery_fee', None)
        else (restaurant.delivery_fee_amount or 0)
    )
    pickup = (
        restaurant.address
        or restaurant.name
        or getattr(restaurant, 'slug', '')
        or 'Restoran'
    )
    phone = (
        customer_phone
        or getattr(order, 'customer_phone', '')
        or order.guest_phone
        or ''
    )
    address = (
        dropoff_address
        or getattr(order, 'delivery_address', '')
        or (order.notes[:200] if order.notes else 'Ünvan göstərilməyib')
    )
    pickup_lat = restaurant.lat if restaurant.lat is not None else 40.3777
    pickup_lng = restaurant.lng if restaurant.lng is not None else 49.8532
    drop_lat = getattr(order, 'delivery_lat', None) or 40.3798
    drop_lng = getattr(order, 'delivery_lng', None) or 49.8465
    dist = getattr(order, 'delivery_distance_km', None)
    return {
        'order': order,
        'restaurant': restaurant,
        'delivery_fee': fee,
        'pickup_address': pickup,
        'dropoff_address': address,
        'customer_phone': phone,
        'customer_name': getattr(order, 'customer_name', '') or '',
        'pickup_lat': pickup_lat,
        'pickup_lng': pickup_lng,
        'dropoff_lat': drop_lat,
        'dropoff_lng': drop_lng,
        'distance_km': dist or Decimal('3.60'),
        'eta_minutes': 14,
        'confirmation_method': 'otp',
    }


def available_couriers(restaurant):
    return Courier.objects.filter(
        restaurant=restaurant,
        is_available=True,
        staff__is_active=True,
        staff__role='courier',
    )


def expire_offer_later(assignment_id: int, delay: int = OFFER_SECONDS):
    def _run():
        import time

        time.sleep(delay)
        try:
            with transaction.atomic():
                a = (
                    DeliveryAssignment.objects.select_for_update()
                    .filter(pk=assignment_id, status='offered')
                    .first()
                )
                if not a:
                    return
                a.status = 'failed'
                a.save(update_fields=['status'])
            _notify_manager(
                a.restaurant,
                a.order,
                title='Kuryer qəbul etmədi',
                message=(
                    f'Sifariş #{a.order_id} — heç kim {OFFER_SECONDS}s '
                    f'ərzində qəbul etmədi'
                ),
            )
            ids = list(
                available_couriers(a.restaurant).values_list('id', flat=True)
            )
            _broadcast_to_couriers(
                ids,
                'offer.expired',
                {'assignment_id': assignment_id, 'order_id': a.order_id},
            )
        except Exception:
            logger.exception('expire_offer failed id=%s', assignment_id)

    threading.Thread(
        target=_run, daemon=True, name=f'delivery-expire-{assignment_id}'
    ).start()


def create_direct_assignment(order, courier: Courier, **extra) -> DeliveryAssignment:
    """Tək boş kuryer — birbaşa təyin, təklif yox."""
    if courier.restaurant_id != order.restaurant_id:
        raise ValidationError('Kuryer sifarişin restoranına aid deyil')

    fields = _base_assignment_fields(order, **extra)
    now = timezone.now()
    assignment = DeliveryAssignment.objects.create(
        **fields,
        courier=courier,
        status='accepted',
        offered_at=None,
        accepted_at=now,
    )
    _set_order_delivering(order)
    payload = serialize_assignment(assignment)
    _broadcast_to_couriers(
        [courier.id],
        'assignment.assigned',
        payload,
    )
    logger.info(
        'Direct assign delivery #%s → courier #%s',
        assignment.id,
        courier.id,
    )
    return assignment


def create_offer_broadcast(order, couriers, **extra) -> DeliveryAssignment:
    """2+ kuryer — hamısına eyni anda təklif."""
    fields = _base_assignment_fields(order, **extra)
    now = timezone.now()
    assignment = DeliveryAssignment.objects.create(
        **fields,
        status='offered',
        offered_at=now,
        offer_expires_at=now + timedelta(seconds=OFFER_SECONDS),
    )
    # Kanbanda "çatdırılır / kuryer axtarılır" görünməsi üçün
    _set_order_delivering(order)

    ids = [c.id for c in couriers]
    payload = serialize_offer(assignment)
    _broadcast_to_couriers(ids, 'offer.new', payload)
    expire_offer_later(assignment.id)
    logger.info(
        'Broadcast offer #%s to %s restaurant couriers',
        assignment.id,
        len(ids),
    )
    return assignment


def assign_courier(order, *, dropoff_address='', customer_phone=''):
    """
    Sifariş ready olanda — yalnız həmin restoranın boş kuryerləri.
    """
    if not is_delivery_order(order):
        return None

    restaurant = order.restaurant
    existing = DeliveryAssignment.objects.filter(order=order).first()
    if existing and existing.status not in ('failed', 'cancelled'):
        # Ünvan/koordinat sifarişdən yenilə (ilk dəfə boş ola bilər)
        fields = _base_assignment_fields(
            order,
            dropoff_address=dropoff_address,
            customer_phone=customer_phone,
        )
        for key in (
            'dropoff_address',
            'customer_phone',
            'customer_name',
            'pickup_address',
            'pickup_lat',
            'pickup_lng',
            'dropoff_lat',
            'dropoff_lng',
            'distance_km',
            'delivery_fee',
        ):
            setattr(existing, key, fields[key])
        existing.save(
            update_fields=[
                'dropoff_address',
                'customer_phone',
                'customer_name',
                'pickup_address',
                'pickup_lat',
                'pickup_lng',
                'dropoff_lat',
                'dropoff_lng',
                'distance_km',
                'delivery_fee',
            ]
        )
        _set_order_delivering(order)
        payload = serialize_assignment(existing)
        if existing.courier_id and existing.status in (
            'accepted',
            'picked_up',
        ):
            _broadcast_to_couriers(
                [existing.courier_id], 'assignment.assigned', payload
            )
        elif existing.status == 'offered':
            ids = list(
                available_couriers(restaurant).values_list('id', flat=True)
            )
            _broadcast_to_couriers(ids, 'offer.new', serialize_offer(existing))
        elif existing.status == 'pending':
            # İndi boş kuryer varsa təyin et
            available = list(available_couriers(restaurant))
            if len(available) == 1:
                existing.delete()
                return create_direct_assignment(
                    order,
                    available[0],
                    dropoff_address=dropoff_address,
                    customer_phone=customer_phone,
                )
            if len(available) >= 2:
                existing.delete()
                return create_offer_broadcast(
                    order,
                    available,
                    dropoff_address=dropoff_address,
                    customer_phone=customer_phone,
                )
        return existing

    if existing:
        existing.delete()

    available = list(available_couriers(restaurant))
    extra = {
        'dropoff_address': dropoff_address,
        'customer_phone': customer_phone,
    }

    if len(available) == 0:
        fields = _base_assignment_fields(order, **extra)
        assignment = DeliveryAssignment.objects.create(
            **fields,
            status='pending',
        )
        _notify_manager(
            restaurant,
            order,
            title='Boş kuryer yoxdur',
            message=(
                f'Sifariş #{order.id} hazırdır, aktiv kuryer yoxdur — '
                f'əl ilə təyin edin'
            ),
        )
        logger.info('No courier for order #%s — pending', order.id)
        return assignment

    if len(available) == 1:
        return create_direct_assignment(order, available[0], **extra)

    return create_offer_broadcast(order, available, **extra)


# Köhnə ad — uyğunluq
def create_and_broadcast_delivery(order, *, dropoff_address='', customer_phone=''):
    return assign_courier(
        order,
        dropoff_address=dropoff_address,
        customer_phone=customer_phone,
    )


def accept_assignment(assignment: DeliveryAssignment, courier: Courier):
    if courier.restaurant_id != assignment.restaurant_id:
        return None, 'Bu sifariş sizin restoranınıza aid deyil'

    with transaction.atomic():
        a = (
            DeliveryAssignment.objects.select_for_update()
            .filter(pk=assignment.pk)
            .first()
        )
        if not a or a.status != 'offered':
            return None, 'Təklif artıq keçərsizdir'
        if a.courier_id and a.courier_id != courier.id:
            return None, 'Artıq başqa kuryerə təyin olunub'

        a.courier = courier
        a.status = 'accepted'
        a.accepted_at = timezone.now()
        a.save(update_fields=['courier', 'status', 'accepted_at'])
        _set_order_delivering(a.order)

    others = list(
        available_couriers(a.restaurant)
        .exclude(pk=courier.pk)
        .values_list('id', flat=True)
    )
    _broadcast_to_couriers(
        others,
        'offer.taken',
        {'assignment_id': a.id, 'order_id': a.order_id},
    )
    return a, None


def ensure_courier_profile(staff) -> Courier | None:
    """StaffUser(role=courier) üçün Courier profili."""
    if not staff or staff.role != 'courier':
        return None
    if not staff.user_id:
        from django.contrib.auth.models import User

        username = f'courier_{staff.restaurant.slug}_{staff.id}'
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={'first_name': staff.display_name[:30]},
        )
        staff.user = user
        staff.save(update_fields=['user'])

    courier, created = Courier.objects.get_or_create(
        staff=staff,
        defaults={
            'user': staff.user,
            'restaurant': staff.restaurant,
            'full_name': staff.display_name,
            'phone': '',
        },
    )
    updates = []
    if courier.restaurant_id != staff.restaurant_id:
        courier.restaurant = staff.restaurant
        updates.append('restaurant')
    if not courier.user_id and staff.user_id:
        courier.user = staff.user
        updates.append('user')
    if updates:
        courier.save(update_fields=updates)
    return courier


def earnings_summary(courier: Courier, *, preset='today'):
    now = timezone.localtime()
    today = now.date()
    if preset == 'week':
        start = today - timedelta(days=today.weekday())
    else:
        start = today
    qs = DeliveryAssignment.objects.filter(
        courier=courier,
        status='delivered',
        delivered_at__date__gte=start,
        delivered_at__date__lte=today,
    )
    agg = qs.aggregate(total=Sum('delivery_fee'))
    total = Decimal(str(agg['total'] or 0)).quantize(Decimal('0.01'))
    rows = qs.order_by('-delivered_at')[:30]
    return {
        'preset': preset,
        'total_amount': f'{total:.2f}',
        'total_deliveries': qs.count(),
        'items': [
            {
                'id': r.id,
                'address': r.dropoff_address,
                'amount': f'{Decimal(str(r.delivery_fee)).quantize(Decimal("0.01")):.2f}',
                'delivered_at': r.delivered_at.isoformat()
                if r.delivered_at
                else None,
            }
            for r in rows
        ],
    }
