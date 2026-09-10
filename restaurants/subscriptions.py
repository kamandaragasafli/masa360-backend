"""Abunə planları və qiymətləndirmə."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

PLAN_PRICES_MONTHLY = {
    'start': Decimal('49'),
    'pro': Decimal('99'),
    'net': Decimal('179'),
}

YEARLY_DISCOUNT = Decimal('0.20')  # 20%
ALLOWED_PLANS = frozenset(PLAN_PRICES_MONTHLY)
ALLOWED_INTERVALS = frozenset({'monthly', 'yearly'})


def monthly_price(plan: str) -> Decimal:
    return PLAN_PRICES_MONTHLY.get(plan, Decimal('0'))


def yearly_price(plan: str) -> Decimal:
    full = monthly_price(plan) * Decimal('12')
    return (full * (Decimal('1') - YEARLY_DISCOUNT)).quantize(Decimal('0.01'))


def price_for(plan: str, interval: str) -> Decimal:
    if interval == 'yearly':
        return yearly_price(plan)
    return monthly_price(plan)


def duration_for(interval: str) -> timedelta:
    if interval == 'yearly':
        return timedelta(days=365)
    return timedelta(days=30)


def compute_expiry(*, interval: str, from_dt=None):
    start = from_dt or timezone.now()
    return start + duration_for(interval)


def subscription_is_active(restaurant) -> bool:
    if not getattr(restaurant, 'subscription_plan', None):
        return False
    expires = getattr(restaurant, 'subscription_expires_at', None)
    if expires is None:
        return True
    return expires > timezone.now()


def days_until_expiry(restaurant) -> int | None:
    expires = getattr(restaurant, 'subscription_expires_at', None)
    if not expires:
        return None
    delta = expires - timezone.now()
    return max(0, delta.days)


def plans_catalog() -> list[dict]:
    rows = []
    for plan_id, monthly in PLAN_PRICES_MONTHLY.items():
        yearly = yearly_price(plan_id)
        rows.append(
            {
                'id': plan_id,
                'monthly_price': str(monthly),
                'yearly_price': str(yearly),
                'yearly_discount_percent': int(YEARLY_DISCOUNT * 100),
            }
        )
    return rows
