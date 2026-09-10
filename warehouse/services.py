from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch, Sum
from django.utils import timezone

from .models import IngredientBatch, RawIngredient, WasteLog

logger = logging.getLogger(__name__)


def _unit_label(unit: str) -> str:
    return dict(RawIngredient.UNIT_CHOICES).get(unit, unit)


def days_until_expiry(expiry: date | None, today: date | None = None) -> int | None:
    if not expiry:
        return None
    today = today or timezone.localdate()
    return (expiry - today).days


def batch_urgency(expiry: date | None, *, warn_days: int = 7) -> str:
    """
    fresh | warn | urgent | expired | none
    Kitchen tone sistemi ilə uyğun.
    """
    d = days_until_expiry(expiry)
    if d is None:
        return 'none'
    if d < 0:
        return 'expired'
    if d <= 1:
        return 'urgent'
    if d <= warn_days:
        return 'warn'
    return 'fresh'


def format_expiry_label(expiry: date | None) -> str:
    d = days_until_expiry(expiry)
    if d is None:
        return 'tarixsiz'
    if d < 0:
        return f'{abs(d)} gün keçib'
    if d == 0:
        return 'bu gün bitir'
    if d == 1:
        return 'sabah bitir'
    return f'{d} gün'


def format_qty(qty: Decimal | float | str, unit: str) -> str:
    q = Decimal(str(qty)).normalize()
    # 2.100 → 2.1, 2.000 → 2
    s = format(q, 'f').rstrip('0').rstrip('.') if '.' in format(q, 'f') else str(q)
    return f'{s} {_unit_label(unit)}'


def serialize_batch(batch: IngredientBatch, *, warn_days: int = 7) -> dict:
    tone = batch_urgency(batch.expiry_date, warn_days=warn_days)
    return {
        'id': batch.id,
        'quantity': str(batch.quantity),
        'remaining_quantity': str(batch.remaining_quantity),
        'remaining_label': format_qty(
            batch.remaining_quantity, batch.ingredient.unit
        ),
        'expiry_date': batch.expiry_date.isoformat() if batch.expiry_date else None,
        'expiry_label': format_expiry_label(batch.expiry_date),
        'days_left': days_until_expiry(batch.expiry_date),
        'tone': tone,
        'supplier': batch.supplier or '',
        'invoice_image': batch.invoice_image.url if batch.invoice_image else None,
        'received_at': batch.received_at.isoformat() if batch.received_at else None,
        'badge': (
            f'{format_qty(batch.remaining_quantity, batch.ingredient.unit)}'
            f' · {format_expiry_label(batch.expiry_date)}'
        ),
    }


def ingredient_expiry_tone(
    batches: list[IngredientBatch],
    *,
    warn_days: int = 7,
) -> str:
    """Kart/ümumi ton — yalnız son istifadə tarixinə görə (stok azlığı qarışmır)."""
    worst = 'none'
    rank = {'none': 0, 'fresh': 1, 'warn': 2, 'urgent': 3, 'expired': 4}
    for b in batches:
        t = batch_urgency(b.expiry_date, warn_days=warn_days)
        if rank.get(t, 0) > rank.get(worst, 0):
            worst = t
    return worst if worst != 'none' else 'fresh'


# Köhnə ad — uyğunluq üçün
def ingredient_stock_tone(
    ingredient: RawIngredient,
    batches: list[IngredientBatch],
    *,
    warn_days: int = 7,
) -> str:
    return ingredient_expiry_tone(batches, warn_days=warn_days)


def serialize_ingredient(
    ingredient: RawIngredient,
    *,
    warn_days: int = 7,
    batches: list[IngredientBatch] | None = None,
) -> dict:
    if batches is None:
        batches = list(
            ingredient.batches.filter(remaining_quantity__gt=0).order_by(
                'expiry_date', 'received_at'
            )
        )
    total = sum((b.remaining_quantity for b in batches), Decimal('0'))
    low = total <= ingredient.min_stock
    tone = ingredient_expiry_tone(batches, warn_days=warn_days)
    return {
        'id': ingredient.id,
        'name': ingredient.name,
        'unit': ingredient.unit,
        'unit_label': _unit_label(ingredient.unit),
        'category_id': ingredient.category_id,
        'category_name': ingredient.category.name if ingredient.category_id else '',
        'min_stock': str(ingredient.min_stock),
        'total_remaining': str(total),
        'total_label': format_qty(total, ingredient.unit),
        'is_low_stock': low,
        'tone': tone,
        'is_active': ingredient.is_active,
        'batches': [
            serialize_batch(b, warn_days=warn_days) for b in batches
        ],
        'batch_count': len(batches),
    }


def stock_alerts(restaurant, *, warn_days: int | None = None):
    warn_days = (
        warn_days
        if warn_days is not None
        else int(getattr(restaurant, 'notify_expiry_days', 7) or 7)
    )
    today = timezone.localdate()
    urgent_cut = today + timedelta(days=1)
    warn_cut = today + timedelta(days=warn_days)

    qs = (
        RawIngredient.objects.filter(restaurant=restaurant, is_active=True)
        .prefetch_related(
            Prefetch(
                'batches',
                queryset=IngredientBatch.objects.filter(
                    remaining_quantity__gt=0
                ).order_by('expiry_date'),
            )
        )
        .select_related('category')
    )

    urgent = []
    low = []
    for ing in qs:
        batches = list(ing.batches.all())
        total = sum((b.remaining_quantity for b in batches), Decimal('0'))
        if any(
            b.expiry_date and b.expiry_date <= urgent_cut for b in batches
        ):
            urgent.append(serialize_ingredient(ing, warn_days=warn_days, batches=batches))
        elif total <= ing.min_stock:
            low.append(serialize_ingredient(ing, warn_days=warn_days, batches=batches))
        elif any(
            b.expiry_date and today < b.expiry_date <= warn_cut for b in batches
        ):
            # warn expiry — banner-də ayrı say
            pass

    expiring_soon = (
        IngredientBatch.objects.filter(
            ingredient__restaurant=restaurant,
            ingredient__is_active=True,
            remaining_quantity__gt=0,
            expiry_date__isnull=False,
            expiry_date__lte=warn_cut,
        )
        .select_related('ingredient')
        .count()
    )

    return {
        'urgent_count': len(urgent),
        'low_stock_count': len(low),
        'expiring_soon_count': expiring_soon,
        'urgent': urgent[:8],
        'low_stock': low[:8],
        'warn_days': warn_days,
        'banner': _banner_text(len(urgent), len(low), expiring_soon),
    }


def _banner_text(urgent: int, low: int, expiring: int) -> str | None:
    parts = []
    if urgent:
        parts.append(f'{urgent} xammal təcili (sabah / keçib)')
    if low:
        parts.append(f'{low} kritik stok')
    if expiring and not urgent:
        parts.append(f'{expiring} partiya tezliklə bitir')
    if not parts:
        return None
    return ' · '.join(parts)


@transaction.atomic
def receive_batch(
    *,
    ingredient: RawIngredient,
    quantity: Decimal,
    expiry_date: date | None = None,
    supplier: str = '',
    note: str = '',
    invoice_image=None,
    user=None,
) -> IngredientBatch:
    qty = Decimal(str(quantity))
    if qty <= 0:
        raise ValueError('Miqdar 0-dan böyük olmalıdır')
    batch = IngredientBatch(
        ingredient=ingredient,
        quantity=qty,
        remaining_quantity=qty,
        expiry_date=expiry_date,
        supplier=(supplier or '')[:120],
        note=(note or '')[:255],
        created_by=user if getattr(user, 'is_authenticated', False) else None,
    )
    if invoice_image:
        batch.invoice_image = invoice_image
    batch.full_clean()
    batch.save()
    return batch


@transaction.atomic
def record_waste(
    *,
    batch: IngredientBatch,
    quantity: Decimal,
    reason: str,
    note: str = '',
    user=None,
) -> WasteLog:
    qty = Decimal(str(quantity))
    if qty <= 0:
        raise ValueError('Miqdar 0-dan böyük olmalıdır')
    if qty > batch.remaining_quantity:
        raise ValueError('Partiyada kifayət qədər miqdar yoxdur')
    batch.remaining_quantity -= qty
    batch.save(update_fields=['remaining_quantity'])
    return WasteLog.objects.create(
        batch=batch,
        quantity=qty,
        reason=reason,
        note=(note or '')[:255],
        created_by=user if getattr(user, 'is_authenticated', False) else None,
    )


@transaction.atomic
def deduct_stock_for_order(order):
    """
    FIFO — sifariş mətbəxə gedəndə (resept varsa).
    Resept yoxdursa heç nə etmir.
    """
    from notifications.services import create_notification

    for order_item in order.items.select_related('menu_item').all():
        menu_item = order_item.menu_item
        if not menu_item:
            continue
        recipe = getattr(menu_item, 'recipe', None)
        if recipe is None:
            continue
        for line in recipe.lines.select_related('ingredient').all():
            needed = Decimal(str(line.quantity)) * order_item.quantity
            batches = (
                IngredientBatch.objects.select_for_update()
                .filter(
                    ingredient=line.ingredient,
                    remaining_quantity__gt=0,
                )
                .order_by('expiry_date', 'received_at')
            )
            for batch in batches:
                if needed <= 0:
                    break
                deduct = min(batch.remaining_quantity, needed)
                batch.remaining_quantity -= deduct
                batch.save(update_fields=['remaining_quantity'])
                needed -= deduct
            if needed > 0:
                try:
                    create_notification(
                        restaurant=order.restaurant,
                        type='low_stock',
                        title='Stok kifayət etmədi',
                        message=(
                            f'{line.ingredient.name} — sifariş #{order.id} '
                            f'üçün çatışmır'
                        ),
                        recipient_role='manager',
                        link='/warehouse',
                        related_order=order,
                    )
                except Exception:
                    logger.exception('stock notify failed')
