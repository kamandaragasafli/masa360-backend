"""Çatdırılma haqqı — Mapbox Directions + restoran tarifləri."""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class DeliveryZoneError(Exception):
    """Ünvan çatdırılma zonasından kənar."""

    def __init__(self, message: str, *, distance_km: float | None = None):
        super().__init__(message)
        self.distance_km = distance_km


# Bakı default — restoran lat/lng boş olanda
DEFAULT_RESTO_LAT = 40.3777
DEFAULT_RESTO_LNG = 49.8532


def _round_money(v: Decimal) -> Decimal:
    return v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Fallback düz xətt (km) — Mapbox cavab verməyəndə."""
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    )
    return 2 * r * asin(sqrt(a))


def road_distance_km(
    resto_lng: float,
    resto_lat: float,
    cust_lng: float,
    cust_lat: float,
) -> float:
    token = getattr(settings, 'MAPBOX_TOKEN', '') or ''
    if not token:
        return haversine_km(resto_lat, resto_lng, cust_lat, cust_lng)

    url = (
        f'https://api.mapbox.com/directions/v5/mapbox/driving/'
        f'{resto_lng},{resto_lat};{cust_lng},{cust_lat}'
    )
    try:
        res = requests.get(
            url,
            params={'access_token': token, 'overview': 'false'},
            timeout=8,
        )
        res.raise_for_status()
        data = res.json()
        routes = data.get('routes') or []
        if not routes:
            return haversine_km(resto_lat, resto_lng, cust_lat, cust_lng)
        return float(routes[0]['distance']) / 1000.0
    except Exception:
        logger.exception('Mapbox directions failed — haversine fallback')
        return haversine_km(resto_lat, resto_lng, cust_lat, cust_lng)


def calculate_delivery_fee(restaurant, customer_lat: float, customer_lng: float):
    """
    Returns (fee: Decimal, distance_km: Decimal, eta_minutes: int).
    Raises DeliveryZoneError if outside radius.
    """
    resto_lat = restaurant.lat if restaurant.lat is not None else DEFAULT_RESTO_LAT
    resto_lng = restaurant.lng if restaurant.lng is not None else DEFAULT_RESTO_LNG

    distance = road_distance_km(
        float(resto_lng), float(resto_lat), float(customer_lng), float(customer_lat)
    )
    max_km = float(restaurant.delivery_radius_km or 5)

    if distance > max_km:
        raise DeliveryZoneError(
            'Təəssüf ki, bu ünvan çatdırılma zonamızdan kənardır',
            distance_km=distance,
        )

    fee_type = restaurant.delivery_fee_type or 'fixed'
    if fee_type == 'distance':
        base = Decimal(str(restaurant.delivery_base_fee or 0))
        per_km = Decimal(str(restaurant.delivery_per_km_fee or 0))
        fee = base + (Decimal(str(distance)) * per_km)
    else:
        fee = Decimal(str(restaurant.delivery_fee_amount or 0))

    fee = _round_money(fee)
    distance_dec = _round_money(Decimal(str(distance)))
    # kobud ETA: 10 dəq baza + 3 dəq/km
    eta = int(10 + distance * 3)
    eta_lo = max(15, eta - 5)
    eta_hi = eta + 10
    return fee, distance_dec, eta_lo, eta_hi
