"""
Dashboard diqqət şeriti — yalnız «bu gün reaksiya lazımdır?» siqnalları.
Detallar Anbar / Mətbəx / Bildiriş bölmələrində qalır.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from menu.models import MenuItem
from orders.models import Order
from payments.models import Payment

from .views import _restaurant

# Mətbəxdə «gecikmiş» həddi (dəqiqə)
DELAYED_MINUTES = 20


class DashboardAttentionView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        now = timezone.now()
        today_start = timezone.localtime().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        alerts = []

        # 1) Menyuda stokda yoxdur
        oos = MenuItem.objects.filter(
            restaurant=restaurant, is_active=True, is_available=False
        ).count()
        if oos:
            alerts.append(
                {
                    'id': 'out_of_stock',
                    'severity': 'warning',
                    'count': oos,
                    'message': (
                        f'{oos} məhsul stokda yoxdur'
                        if oos != 1
                        else '1 məhsul stokda yoxdur'
                    ),
                    'link': '/menu',
                }
            )

        # 2) Gecikmiş mətbəx sifarişləri
        cutoff = now - timedelta(minutes=DELAYED_MINUTES)
        delayed = Order.objects.filter(
            restaurant=restaurant,
            status__in=('received', 'preparing'),
        ).filter(
            Q(preparing_at__lt=cutoff)
            | Q(preparing_at__isnull=True, created_at__lt=cutoff)
        ).count()
        if delayed:
            alerts.append(
                {
                    'id': 'delayed_orders',
                    'severity': 'critical',
                    'count': delayed,
                    'message': (
                        f'{delayed} sifariş gecikir ({DELAYED_MINUTES}+ dəq)'
                        if delayed != 1
                        else f'1 sifariş gecikir ({DELAYED_MINUTES}+ dəq)'
                    ),
                    'link': '/kitchen',
                }
            )

        # 3) Bugünkü uğursuz ödənişlər
        failed_pay = Payment.objects.filter(
            restaurant=restaurant,
            status='failed',
            created_at__gte=today_start,
        ).count()
        if failed_pay:
            alerts.append(
                {
                    'id': 'payment_failed',
                    'severity': 'critical',
                    'count': failed_pay,
                    'message': (
                        f'{failed_pay} uğursuz ödəniş'
                        if failed_pay != 1
                        else '1 uğursuz ödəniş'
                    ),
                    'link': '/alert',
                }
            )

        # 4) Anbar — real partiya / stok
        try:
            from warehouse.services import stock_alerts

            wh = stock_alerts(restaurant)
            if wh['urgent_count'] or wh['low_stock_count']:
                n = wh['urgent_count'] + wh['low_stock_count']
                alerts.append(
                    {
                        'id': 'warehouse',
                        'severity': 'critical' if wh['urgent_count'] else 'warning',
                        'count': n,
                        'message': wh['banner']
                        or f'{n} anbar xəbərdarlığı',
                        'link': '/warehouse',
                    }
                )
        except Exception:
            pass

        # 5) Digər oxunmamış kritik bildirişlər (yuxarıdakılara düşməyənlər)
        try:
            from notifications.models import Notification

            covered = {
                'payment_failed',
                'low_stock',
                'expiry_warning',
                'order_ready',  # operativ, banner-ə yığmırıq — ofisiant axını
            }
            other_critical = (
                Notification.objects.filter(
                    restaurant=restaurant,
                    is_read=False,
                    priority='critical',
                    created_at__gte=now - timedelta(days=1),
                )
                .exclude(type__in=covered)
                .count()
            )
            if other_critical:
                alerts.append(
                    {
                        'id': 'critical_alerts',
                        'severity': 'critical',
                        'count': other_critical,
                        'message': (
                            f'{other_critical} kritik bildiriş'
                            if other_critical != 1
                            else '1 kritik bildiriş'
                        ),
                        'link': '/alert',
                    }
                )
        except Exception:
            pass

        level = 'ok'
        if any(a['severity'] == 'critical' for a in alerts):
            level = 'critical'
        elif alerts:
            level = 'warning'

        return Response(
            {
                'level': level,
                'total': sum(a['count'] for a in alerts),
                'alerts': alerts,
            }
        )
