from datetime import timedelta

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.tenancy import resolve_restaurant

from .models import Notification
from .services import serialize_notification

ARCHIVE_DAYS = 7


def _restaurant(request):
    return resolve_restaurant(request)


def _active_qs(restaurant):
    cutoff = timezone.now() - timedelta(days=ARCHIVE_DAYS)
    return Notification.objects.filter(
        restaurant=restaurant, created_at__gte=cutoff
    )


class NotificationListView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        qs = _active_qs(restaurant)
        filt = request.query_params.get('filter', 'all')
        if filt == 'unread':
            qs = qs.filter(is_read=False)
        elif filt == 'critical':
            qs = qs.filter(priority='critical')

        role = request.query_params.get('role')
        if role and role != 'all':
            qs = qs.filter(recipient_role__in=[role, 'all'])

        page = max(1, int(request.query_params.get('page', 1)))
        page_size = min(100, max(10, int(request.query_params.get('page_size', 40))))
        total = qs.count()
        offset = (page - 1) * page_size
        rows = [serialize_notification(n) for n in qs[offset : offset + page_size]]

        unread = _active_qs(restaurant).filter(is_read=False).count()
        critical_unread = (
            _active_qs(restaurant)
            .filter(is_read=False, priority='critical')
            .count()
        )

        return Response(
            {
                'count': total,
                'page': page,
                'page_size': page_size,
                'unread_count': unread,
                'critical_unread': critical_unread,
                'results': rows,
            }
        )


class NotificationUnreadCountView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        qs = _active_qs(restaurant).filter(is_read=False)
        return Response(
            {
                'unread_count': qs.count(),
                'critical_unread': qs.filter(priority='critical').count(),
            }
        )


class NotificationMarkReadView(APIView):
    def post(self, request, pk):
        restaurant = _restaurant(request)
        n = Notification.objects.filter(pk=pk, restaurant=restaurant).first()
        if not n:
            return Response({'detail': 'Bildiriş tapılmadı'}, status=404)
        if not n.is_read:
            n.is_read = True
            n.save(update_fields=['is_read'])
        return Response(serialize_notification(n))


class NotificationMarkAllReadView(APIView):
    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        updated = (
            _active_qs(restaurant)
            .filter(is_read=False)
            .update(is_read=True)
        )
        return Response({'updated': updated})
