"""Onlayn çatdırılma — ictimai quote + sifariş."""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote

import requests
from django.conf import settings
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from menu.models import MenuItem
from notifications.services import create_notification
from orders.kot import enqueue_kitchen_tickets
from orders.models import Order, OrderItem
from orders.realtime import broadcast_order_event
from restaurants.models import Restaurant

from delivery.fees import DeliveryZoneError, calculate_delivery_fee


def _restaurant(slug: str):
    return Restaurant.objects.filter(slug=slug, is_active=True).first()


def _geocode_address(query: str, *, proximity=None):
    """Mapbox forward geocode — Bakı proximity default."""
    token = getattr(settings, 'MAPBOX_TOKEN', '') or ''
    if not token or not query.strip():
        return None
    prox = proximity or (49.8532, 40.3777)  # lng, lat
    try:
        res = requests.get(
            'https://api.mapbox.com/geocoding/v5/mapbox.places/'
            f'{quote(query.strip())}.json',
            params={
                'access_token': token,
                'country': 'az',
                'language': 'az',
                'limit': 1,
                'proximity': f'{prox[0]},{prox[1]}',
            },
            timeout=8,
        )
        res.raise_for_status()
        feats = res.json().get('features') or []
        if not feats:
            return None
        f0 = feats[0]
        lng, lat = f0['center']
        return {
            'lat': float(lat),
            'lng': float(lng),
            'label': f0.get('place_name') or query.strip(),
        }
    except Exception:
        return None


class DeliveryGeocodeView(APIView):
    """POST /api/public/delivery/geocode/ { slug?, address }"""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        address = (request.data.get('address') or '').strip()
        if len(address) < 3:
            return Response(
                {'detail': 'Ünvan çox qısadır'}, status=400
            )
        slug = (request.data.get('slug') or 'surfues-resto').strip()
        restaurant = _restaurant(slug)
        proximity = None
        if restaurant and restaurant.lng is not None and restaurant.lat is not None:
            proximity = (restaurant.lng, restaurant.lat)
        hit = _geocode_address(address, proximity=proximity)
        if not hit:
            return Response(
                {
                    'ok': False,
                    'detail': 'Ünvan xəritədə tapılmadı — pin seçin',
                },
                status=404,
            )
        return Response({'ok': True, **hit})


class DeliveryQuoteView(APIView):
    """
    POST /api/public/delivery/quote/
    { slug, lat, lng }
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        slug = (request.data.get('slug') or 'surfues-resto').strip()
        restaurant = _restaurant(slug)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        if not restaurant.delivery_enabled:
            return Response(
                {'detail': 'Bu restoran çatdırılma qəbul etmir'},
                status=400,
            )
        try:
            lat = float(request.data.get('lat'))
            lng = float(request.data.get('lng'))
        except (TypeError, ValueError):
            return Response(
                {'detail': 'lat/lng tələb olunur'}, status=400
            )

        try:
            fee, distance, eta_lo, eta_hi = calculate_delivery_fee(
                restaurant, lat, lng
            )
        except DeliveryZoneError as e:
            return Response(
                {
                    'ok': False,
                    'code': 'out_of_zone',
                    'detail': str(e),
                    'distance_km': (
                        round(e.distance_km, 2) if e.distance_km else None
                    ),
                    'max_radius_km': str(restaurant.delivery_radius_km),
                },
                status=400,
            )

        return Response(
            {
                'ok': True,
                'delivery_fee': str(fee),
                'distance_km': str(distance),
                'eta_minutes_min': eta_lo,
                'eta_minutes_max': eta_hi,
                'eta_label': f'{eta_lo}-{eta_hi} dəq',
            }
        )


class OnlineOrderCreateView(APIView):
    """
    POST /api/public/delivery/orders/
    Onlayn checkout — order_type=delivery, source=online.
    """

    authentication_classes = []
    permission_classes = []

    @transaction.atomic
    def post(self, request):
        slug = (request.data.get('slug') or 'surfues-resto').strip()
        restaurant = _restaurant(slug)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        if not restaurant.delivery_enabled:
            return Response(
                {'detail': 'Çatdırılma deaktivdir'}, status=400
            )

        customer_name = (request.data.get('customer_name') or '').strip()
        customer_phone = (request.data.get('customer_phone') or '').strip()
        address = (request.data.get('delivery_address') or '').strip()
        note = (request.data.get('delivery_note') or '').strip()
        items = request.data.get('items') or []

        if not customer_name or not customer_phone:
            return Response(
                {'detail': 'Ad və telefon tələb olunur'}, status=400
            )
        if not address:
            return Response({'detail': 'Ünvan tələb olunur'}, status=400)
        if not items:
            return Response({'detail': 'Səbət boşdur'}, status=400)

        try:
            lat = float(request.data.get('delivery_lat'))
            lng = float(request.data.get('delivery_lng'))
        except (TypeError, ValueError):
            hit = _geocode_address(
                address,
                proximity=(
                    (restaurant.lng, restaurant.lat)
                    if restaurant.lng is not None and restaurant.lat is not None
                    else None
                ),
            )
            if hit:
                lat, lng = hit['lat'], hit['lng']
            else:
                lat, lng = 40.3798, 49.8465

        try:
            fee, distance, eta_lo, eta_hi = calculate_delivery_fee(
                restaurant, lat, lng
            )
        except DeliveryZoneError as e:
            return Response(
                {
                    'detail': str(e),
                    'code': 'out_of_zone',
                },
                status=400,
            )

        item_ids = [int(x['menu_item_id']) for x in items]
        menu_map = {
            m.id: m
            for m in MenuItem.objects.filter(
                restaurant=restaurant, pk__in=item_ids, is_active=True
            )
        }

        lines = []
        subtotal = Decimal('0.00')
        for line in items:
            mid = int(line['menu_item_id'])
            menu_item = menu_map.get(mid)
            if not menu_item or not menu_item.is_available:
                return Response(
                    {'detail': f'Məhsul əlçatan deyil: {mid}'},
                    status=400,
                )
            qty = max(1, int(line.get('quantity') or 1))
            unit = Decimal(menu_item.price)
            subtotal += unit * qty
            lines.append(
                (
                    menu_item,
                    qty,
                    unit,
                    (line.get('special_instructions') or '')[:255],
                )
            )

        total = subtotal + fee
        order = Order.objects.create(
            restaurant=restaurant,
            table=None,
            source='online',
            order_type='delivery',
            status='received',
            total_amount=total,
            notes=note,
            guest_phone=customer_phone,
            delivery_address=address[:500],
            delivery_lat=lat,
            delivery_lng=lng,
            customer_name=customer_name[:100],
            customer_phone=customer_phone[:20],
            delivery_note=note[:255],
            delivery_fee=fee,
            delivery_distance_km=distance,
            delivery_payment_method='cash_on_delivery',
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=qty,
                    unit_price=unit,
                    special_instructions=instr,
                )
                for menu_item, qty, unit, instr in lines
            ]
        )

        order = (
            Order.objects.filter(pk=order.pk)
            .prefetch_related('items__menu_item')
            .first()
        )

        from orders.views import _serialize_order, _slug_for

        payload = _serialize_order(order)
        broadcast_order_event(
            _slug_for(restaurant), 'order.created', payload
        )
        create_notification(
            restaurant=restaurant,
            type='new_order',
            message=f'Onlayn çatdırılma #{order.id} — {address[:40]}',
            link='/board',
            related_order=order,
        )
        try:
            enqueue_kitchen_tickets(order)
        except Exception:
            pass

        return Response(
            {
                **payload,
                'delivery_fee': str(fee),
                'distance_km': str(distance),
                'eta_label': f'{eta_lo}-{eta_hi} dəq',
                'subtotal': str(subtotal),
            },
            status=201,
        )
