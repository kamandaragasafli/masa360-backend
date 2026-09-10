"""
Hesabat aggregasiyaları — dövr müqayisəsi və qərar dəstəyi.
Böyüdükcə DailySalesSummary + Celery ilə əvvəlcədən hesablana bilər.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncHour
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from openpyxl import Workbook
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import Payment
from restaurants.tenancy import resolve_restaurant

from .models import Order, OrderItem


def _restaurant(request):
    return resolve_restaurant(request)


def _period_bounds(request):
    """
    preset: day|week|month|quarter|custom
    Qaytarır: (start_dt, end_dt, prev_start, prev_end, label)
    """
    preset = request.query_params.get('preset', 'month')
    now = timezone.localtime()
    today = now.date()
    tz = timezone.get_current_timezone()

    if preset == 'day':
        start = end = today
    elif preset == 'week':
        start = today - timedelta(days=today.weekday())
        end = today
    elif preset == 'quarter':
        q = (today.month - 1) // 3
        start = today.replace(month=q * 3 + 1, day=1)
        end = today
    elif preset == 'custom':
        start = parse_date(request.query_params.get('date_from') or '') or (
            today - timedelta(days=30)
        )
        end = parse_date(request.query_params.get('date_to') or '') or today
    else:  # month
        start = today.replace(day=1)
        end = today

    days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    def bounds(d0, d1):
        return (
            timezone.make_aware(datetime.combine(d0, time.min), tz),
            timezone.make_aware(datetime.combine(d1, time.max), tz),
        )

    start_dt, end_dt = bounds(start, end)
    prev_start_dt, prev_end_dt = bounds(prev_start, prev_end)
    return {
        'start': start,
        'end': end,
        'start_dt': start_dt,
        'end_dt': end_dt,
        'prev_start': prev_start,
        'prev_end': prev_end,
        'prev_start_dt': prev_start_dt,
        'prev_end_dt': prev_end_dt,
        'preset': preset,
    }


def _pct_change(current, previous):
    cur = Decimal(current or 0)
    prev = Decimal(previous or 0)
    if prev == 0:
        return None if cur == 0 else 100.0
    return float(((cur - prev) / prev) * 100)


def _money(v):
    return str(Decimal(v or 0).quantize(Decimal('0.01')))


def _completed_qs(restaurant, start_dt, end_dt):
    return Order.objects.filter(
        restaurant=restaurant,
        status='completed',
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    )


def _finance_block(restaurant, start_dt, end_dt):
    qs = _completed_qs(restaurant, start_dt, end_dt)
    agg = qs.aggregate(
        revenue=Coalesce(
            Sum('total_amount'),
            Value(Decimal('0')),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        orders=Count('id'),
    )
    revenue = agg['revenue'] or Decimal('0')
    orders = agg['orders'] or 0
    aov = (revenue / orders) if orders else Decimal('0')

    vat_pct = Decimal(restaurant.vat_percent or 0)
    # ƏDV daxil qiymət fərz: net = gross / (1+vat), vat = gross - net
    if vat_pct > 0:
        net = revenue / (1 + vat_pct / 100)
        vat_amount = revenue - net
    else:
        net = revenue
        vat_amount = Decimal('0')

    payments = (
        Payment.objects.filter(
            restaurant=restaurant,
            status='paid',
            paid_at__gte=start_dt,
            paid_at__lte=end_dt,
        )
        .values('method')
        .annotate(
            total=Coalesce(
                Sum('amount'),
                Value(Decimal('0')),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            count=Count('id'),
        )
    )
    method_labels = dict(Payment.METHOD_CHOICES)
    by_method = [
        {
            'method': p['method'],
            'label': method_labels.get(p['method'], p['method']),
            'total': _money(p['total']),
            'count': p['count'],
        }
        for p in payments
    ]

    # Ödənişsiz tamamlanan sifarişlər — nağd kimi göstər (POS/ofisiant)
    paid_order_ids = Payment.objects.filter(
        restaurant=restaurant,
        status='paid',
        order__created_at__gte=start_dt,
        order__created_at__lte=end_dt,
    ).values_list('order_id', flat=True)
    unpaid_cash = (
        qs.exclude(id__in=paid_order_ids).aggregate(
            total=Coalesce(
                Sum('total_amount'),
                Value(Decimal('0')),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            count=Count('id'),
        )
    )
    if unpaid_cash['count']:
        # merge into cash
        found = False
        for row in by_method:
            if row['method'] == 'cash':
                row['total'] = _money(
                    Decimal(row['total']) + Decimal(unpaid_cash['total'] or 0)
                )
                row['count'] += unpaid_cash['count']
                found = True
                break
        if not found:
            by_method.append(
                {
                    'method': 'cash',
                    'label': 'Nağd',
                    'total': _money(unpaid_cash['total']),
                    'count': unpaid_cash['count'],
                }
            )

    cancelled = Order.objects.filter(
        restaurant=restaurant,
        status='cancelled',
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).aggregate(
        total=Coalesce(
            Sum('total_amount'),
            Value(Decimal('0')),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
        count=Count('id'),
    )

    return {
        'revenue': _money(revenue),
        'net_ex_vat': _money(net),
        'vat_amount': _money(vat_amount),
        'vat_percent': str(vat_pct),
        'orders': orders,
        'aov': _money(aov),
        'cancelled_count': cancelled['count'] or 0,
        'cancelled_amount': _money(cancelled['total']),
        'by_payment_method': by_method,
    }


class ReportOverviewView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        p = _period_bounds(request)
        current = _finance_block(restaurant, p['start_dt'], p['end_dt'])
        previous = _finance_block(
            restaurant, p['prev_start_dt'], p['prev_end_dt']
        )

        return Response(
            {
                'period': {
                    'preset': p['preset'],
                    'date_from': p['start'].isoformat(),
                    'date_to': p['end'].isoformat(),
                    'prev_from': p['prev_start'].isoformat(),
                    'prev_to': p['prev_end'].isoformat(),
                },
                'currency': restaurant.currency or 'AZN',
                'finance': current,
                'finance_previous': previous,
                'comparison': {
                    'revenue_pct': _pct_change(
                        current['revenue'], previous['revenue']
                    ),
                    'orders_pct': _pct_change(
                        current['orders'], previous['orders']
                    ),
                    'aov_pct': _pct_change(current['aov'], previous['aov']),
                },
            }
        )


class ReportSalesView(APIView):
    """Saat/gün üzrə satış + kateqoriya."""

    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        p = _period_bounds(request)
        qs = _completed_qs(restaurant, p['start_dt'], p['end_dt'])

        by_hour = (
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
            .order_by('hour')
        )
        # Heat map: weekday 0-6 × hour 0-23
        heat = [[0.0 for _ in range(24)] for _ in range(7)]
        for row in by_hour:
            if not row['hour']:
                continue
            local = timezone.localtime(row['hour'])
            heat[local.weekday()][local.hour] += float(row['revenue'] or 0)

        by_day = (
            qs.annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(
                revenue=Coalesce(
                    Sum('total_amount'),
                    Value(Decimal('0')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
                orders=Count('id'),
            )
            .order_by('day')
        )

        weekday_vs_weekend = {'weekday': Decimal('0'), 'weekend': Decimal('0')}
        for row in by_day:
            if not row['day']:
                continue
            if row['day'].weekday() >= 5:
                weekday_vs_weekend['weekend'] += row['revenue'] or 0
            else:
                weekday_vs_weekend['weekday'] += row['revenue'] or 0

        # Kateqoriya
        cat_rows = (
            OrderItem.objects.filter(order__in=qs)
            .values('menu_item__category__name')
            .annotate(
                revenue=Coalesce(
                    Sum(F('unit_price') * F('quantity')),
                    Value(Decimal('0')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
                qty=Sum('quantity'),
            )
            .order_by('-revenue')
        )
        categories = [
            {
                'name': c['menu_item__category__name'] or 'Kateqoriyasız',
                'revenue': _money(c['revenue']),
                'qty': c['qty'] or 0,
            }
            for c in cat_rows
        ]

        aov_trend = [
            {
                'date': r['day'].isoformat(),
                'revenue': _money(r['revenue']),
                'orders': r['orders'],
                'aov': _money(
                    (r['revenue'] / r['orders']) if r['orders'] else 0
                ),
            }
            for r in by_day
        ]

        return Response(
            {
                'period': {
                    'date_from': p['start'].isoformat(),
                    'date_to': p['end'].isoformat(),
                },
                'heatmap': {
                    'weekdays': [
                        'B.e.',
                        'Ç.a.',
                        'Çər.',
                        'C.a.',
                        'Cümə',
                        'Şən.',
                        'Baz.',
                    ],
                    'hours': list(range(24)),
                    'values': heat,
                },
                'weekday_vs_weekend': {
                    'weekday': _money(weekday_vs_weekend['weekday']),
                    'weekend': _money(weekday_vs_weekend['weekend']),
                },
                'categories': categories,
                'aov_trend': aov_trend,
            }
        )


class ReportProductsView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        p = _period_bounds(request)
        qs = _completed_qs(restaurant, p['start_dt'], p['end_dt'])
        cancelled = Order.objects.filter(
            restaurant=restaurant,
            status='cancelled',
            created_at__gte=p['start_dt'],
            created_at__lte=p['end_dt'],
        )

        products = (
            OrderItem.objects.filter(order__in=qs)
            .values('menu_item_id', 'menu_item__name', 'menu_item__price')
            .annotate(
                qty=Sum('quantity'),
                revenue=Coalesce(
                    Sum(F('unit_price') * F('quantity')),
                    Value(Decimal('0')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
            )
        )
        product_list = list(products)
        by_qty = sorted(product_list, key=lambda x: x['qty'] or 0, reverse=True)
        by_rev = sorted(
            product_list, key=lambda x: x['revenue'] or 0, reverse=True
        )

        cancelled_items = (
            OrderItem.objects.filter(order__in=cancelled)
            .values('menu_item__name')
            .annotate(qty=Sum('quantity'))
            .order_by('-qty')[:10]
        )

        def row(p):
            return {
                'id': p['menu_item_id'],
                'name': p['menu_item__name'],
                'qty': p['qty'] or 0,
                'revenue': _money(p['revenue']),
                'unit_price': _money(p['menu_item__price']),
            }

        return Response(
            {
                'period': {
                    'date_from': p['start'].isoformat(),
                    'date_to': p['end'].isoformat(),
                },
                'top_by_qty': [row(x) for x in by_qty[:15]],
                'top_by_revenue': [row(x) for x in by_rev[:15]],
                'bottom_by_qty': [row(x) for x in list(reversed(by_qty))[:10]],
                'cancelled_items': [
                    {'name': c['menu_item__name'], 'qty': c['qty'] or 0}
                    for c in cancelled_items
                ],
            }
        )


class ReportOpsView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        p = _period_bounds(request)
        qs = _completed_qs(restaurant, p['start_dt'], p['end_dt']).filter(
            preparing_at__isnull=False, ready_at__isnull=False
        )

        # Orta mətbəx vaxtı (dəqiqə)
        kitchen_times = []
        for o in qs.only('preparing_at', 'ready_at')[:500]:
            secs = (o.ready_at - o.preparing_at).total_seconds()
            if secs >= 0:
                kitchen_times.append(secs / 60)

        avg_kitchen = (
            sum(kitchen_times) / len(kitchen_times) if kitchen_times else None
        )

        staff = (
            _completed_qs(restaurant, p['start_dt'], p['end_dt'])
            .filter(served_by__isnull=False)
            .values('served_by_id', 'served_by__full_name')
            .annotate(
                orders=Count('id'),
                revenue=Coalesce(
                    Sum('total_amount'),
                    Value(Decimal('0')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
            )
            .order_by('-revenue')[:15]
        )

        # Masa dövriyyəsi
        days = max(1, (p['end'] - p['start']).days + 1)
        turnover = (
            _completed_qs(restaurant, p['start_dt'], p['end_dt'])
            .filter(table__isnull=False)
            .values('table__number')
            .annotate(uses=Count('id'))
            .order_by('-uses')[:20]
        )

        return Response(
            {
                'period': {
                    'date_from': p['start'].isoformat(),
                    'date_to': p['end'].isoformat(),
                },
                'avg_kitchen_minutes': round(avg_kitchen, 1)
                if avg_kitchen is not None
                else None,
                'kitchen_samples': len(kitchen_times),
                'staff': [
                    {
                        'id': s['served_by_id'],
                        'name': s['served_by__full_name'] or '—',
                        'orders': s['orders'],
                        'revenue': _money(s['revenue']),
                    }
                    for s in staff
                ],
                'table_turnover': [
                    {
                        'table': t['table__number'],
                        'uses': t['uses'],
                        'per_day': round(t['uses'] / days, 2),
                    }
                    for t in turnover
                ],
            }
        )


class ReportFinanceExportView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        p = _period_bounds(request)
        fin = _finance_block(restaurant, p['start_dt'], p['end_dt'])
        prev = _finance_block(restaurant, p['prev_start_dt'], p['prev_end_dt'])

        wb = Workbook()
        ws = wb.active
        ws.title = 'Maliyye'
        ws.append(['Restoran', restaurant.name or restaurant.slug])
        ws.append(
            [
                'Dövr',
                f"{p['start'].isoformat()} — {p['end'].isoformat()}",
            ]
        )
        ws.append(
            [
                'Əvvəlki dövr',
                f"{p['prev_start'].isoformat()} — {p['prev_end'].isoformat()}",
            ]
        )
        ws.append([])
        ws.append(['Göstərici', 'Cari', 'Əvvəlki', 'Dəyişim %'])
        rows = [
            ('Ümumi dövriyyə', fin['revenue'], prev['revenue']),
            ('Xalis (ƏDV-siz)', fin['net_ex_vat'], prev['net_ex_vat']),
            ('ƏDV', fin['vat_amount'], prev['vat_amount']),
            ('Sifariş sayı', fin['orders'], prev['orders']),
            ('Orta çek', fin['aov'], prev['aov']),
            (
                'Ləğv sayı',
                fin['cancelled_count'],
                prev['cancelled_count'],
            ),
        ]
        for label, cur, prv in rows:
            ws.append([label, cur, prv, _pct_change(cur, prv)])

        ws.append([])
        ws.append(['Ödəniş metodu', 'Məbləğ', 'Say'])
        for m in fin['by_payment_method']:
            ws.append([m['label'], m['total'], m['count']])

        # Məhsul vərəqi
        ws2 = wb.create_sheet('Mehsullar')
        ws2.append(['Məhsul', 'Say', 'Gəlir'])
        qs = _completed_qs(restaurant, p['start_dt'], p['end_dt'])
        for row in (
            OrderItem.objects.filter(order__in=qs)
            .values('menu_item__name')
            .annotate(
                qty=Sum('quantity'),
                revenue=Sum(F('unit_price') * F('quantity')),
            )
            .order_by('-revenue')[:100]
        ):
            ws2.append(
                [
                    row['menu_item__name'],
                    row['qty'] or 0,
                    float(row['revenue'] or 0),
                ]
            )

        buf = BytesIO()
        wb.save(buf)
        filename = (
            f"hesabat-{p['start'].isoformat()}-{p['end'].isoformat()}.xlsx"
        )
        resp = HttpResponse(
            buf.getvalue(),
            content_type=(
                'application/vnd.openxmlformats-officedocument'
                '.spreadsheetml.sheet'
            ),
        )
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp
