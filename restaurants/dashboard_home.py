"""
Ana səhifə dashboard — bu günün real satış/stok məlumatı (bir endpoint).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncHour
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from menu.models import MenuItem
from orders.models import Order, OrderItem

from .views import _restaurant

COLORS = ['#d94a2b', '#14b8a6', '#f5c542', '#6366f1', '#0ea5e9', '#a855f7']


def _money(v):
    return str(Decimal(v or 0).quantize(Decimal('0.01')))


def _pct_change(current, previous):
    cur = Decimal(current or 0)
    prev = Decimal(previous or 0)
    if prev == 0:
        return None if cur == 0 else 100.0
    return round(float(((cur - prev) / prev) * 100), 1)


def _day_bounds(day):
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(day, time.min), tz),
        timezone.make_aware(datetime.combine(day, time.max), tz),
    )


def _completed(restaurant, start_dt, end_dt):
    return Order.objects.filter(
        restaurant=restaurant,
        status='completed',
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    )


def _item_image_url(item, request):
    if not item:
        return None
    if item.image:
        if request:
            return request.build_absolute_uri(item.image.url)
        return item.image.url
    return item.image_url or None


class DashboardHomeView(APIView):
    """GET /api/restaurants/dashboard/home/?slug=..."""

    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        start_dt, end_dt = _day_bounds(today)
        prev_start, prev_end = _day_bounds(yesterday)

        qs = _completed(restaurant, start_dt, end_dt)
        prev_qs = _completed(restaurant, prev_start, prev_end)

        def stats_for(q):
            agg = q.aggregate(
                revenue=Coalesce(
                    Sum('total_amount'),
                    Value(Decimal('0')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
                orders=Count('id'),
                dine_in=Count('id', filter=Q(table__isnull=False)),
                takeaway=Count('id', filter=Q(table__isnull=True)),
            )
            return {
                'revenue': agg['revenue'] or Decimal('0'),
                'orders': agg['orders'] or 0,
                'dine_in': agg['dine_in'] or 0,
                'takeaway': agg['takeaway'] or 0,
            }

        cur = stats_for(qs)
        prev = stats_for(prev_qs)        # Saatlıq satış (açılış–bağlanış və ya 10–22)
        open_h = restaurant.opening_time.hour if restaurant.opening_time else 10
        close_h = restaurant.closing_time.hour if restaurant.closing_time else 22
        if close_h <= open_h:
            hours = list(range(open_h, 24)) + list(range(0, close_h + 1))
        else:
            hours = list(range(open_h, close_h + 1))

        by_hour_rows = (
            qs.annotate(hour=TruncHour('created_at'))
            .values('hour')
            .annotate(
                revenue=Coalesce(
                    Sum('total_amount'),
                    Value(Decimal('0')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
                orders=Count('id'),
            )
        )
        hour_map = {}
        for row in by_hour_rows:
            if not row['hour']:
                continue
            local = timezone.localtime(row['hour'])
            hour_map[local.hour] = {
                'revenue': float(row['revenue'] or 0),
                'orders': row['orders'] or 0,
            }

        hourly = []
        for h in hours:
            data = hour_map.get(h, {'revenue': 0.0, 'orders': 0})
            hourly.append(
                {
                    'hour': h,
                    'label': f'{h:02d}:00',
                    'revenue': _money(data['revenue']),
                    'orders': data['orders'],
                }
            )

        # Kateqoriya payı
        cat_rows = (
            OrderItem.objects.filter(order__in=qs)
            .values('menu_item__category__name')
            .annotate(
                revenue=Coalesce(
                    Sum(F('unit_price') * F('quantity')),
                    Value(Decimal('0')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )
            .order_by('-revenue')
        )
        cat_list = list(cat_rows)
        cat_total = sum((c['revenue'] or Decimal('0')) for c in cat_list) or Decimal(
            '0'
        )
        categories = []
        for i, c in enumerate(cat_list[:6]):
            rev = c['revenue'] or Decimal('0')
            pct = float((rev / cat_total * 100) if cat_total else 0)
            categories.append(
                {
                    'name': c['menu_item__category__name'] or 'Digər',
                    'revenue': _money(rev),
                    'pct': round(pct, 1),
                    'color': COLORS[i % len(COLORS)],
                }
            )

        # Populyar məhsullar
        top = (
            OrderItem.objects.filter(order__in=qs)
            .values('menu_item_id', 'menu_item__name')
            .annotate(qty=Sum('quantity'))
            .order_by('-qty')[:5]
        )
        item_ids = [t['menu_item_id'] for t in top if t['menu_item_id']]
        items_map = {
            m.id: m
            for m in MenuItem.objects.filter(pk__in=item_ids)
        }
        popular = [
            {
                'id': t['menu_item_id'],
                'name': t['menu_item__name'],
                'qty': t['qty'] or 0,
                'image_url': _item_image_url(
                    items_map.get(t['menu_item_id']), request
                ),
            }
            for t in top
        ]

        # Stokda yoxdur
        oos_qs = MenuItem.objects.filter(
            restaurant=restaurant, is_active=True, is_available=False
        ).order_by('name')[:8]
        out_of_stock = [
            {
                'id': m.id,
                'name': m.name,
                'image_url': _item_image_url(m, request),
                'note': 'Stokda yoxdur',
            }
            for m in oos_qs
        ]

        return Response(
            {
                'date': today.isoformat(),
                'currency': restaurant.currency or 'AZN',
                'stats': {
                    'revenue': _money(cur['revenue']),
                    'orders': cur['orders'],
                    'dine_in': cur['dine_in'],
                    'takeaway': cur['takeaway'],
                    'revenue_pct': _pct_change(cur['revenue'], prev['revenue']),
                    'orders_pct': _pct_change(cur['orders'], prev['orders']),
                    'dine_in_pct': _pct_change(cur['dine_in'], prev['dine_in']),
                    'takeaway_pct': _pct_change(cur['takeaway'], prev['takeaway']),
                },
                'hourly': hourly,
                'categories': categories,
                'popular': popular,
                'out_of_stock': out_of_stock,
            }
        )
