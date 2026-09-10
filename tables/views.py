from django.db.models import IntegerField, Prefetch
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.services import create_notification
from orders.kanban import serialize_kanban_card
from orders.models import Order
from orders.realtime import broadcast_order_event
from restaurants.tenancy import resolve_restaurant

from .models import FloorElement, Reservation, Table
from .placement import find_free_position
from .serializers import ACTIVE_STATUSES, FloorPlanSerializer, TableSerializer


def _get_restaurant(request):
    return resolve_restaurant(request)


def _tables_qs(restaurant=None):
    active_orders = Prefetch(
        'orders',
        queryset=Order.objects.filter(status__in=ACTIVE_STATUSES)
        .select_related()
        .prefetch_related('items__menu_item')
        .order_by('-created_at'),
    )
    upcoming = Prefetch(
        'reservations',
        queryset=Reservation.objects.filter(
            status='pending',
            reserved_for__gte=timezone.now(),
        ).order_by('reserved_for'),
    )
    qs = (
        Table.objects.select_related('restaurant')
        .prefetch_related(active_orders, upcoming)
    )
    if restaurant is not None:
        qs = qs.filter(restaurant=restaurant)
    return qs.annotate(number_int=Cast('number', IntegerField())).order_by(
        'number_int', 'number'
    )


class TableListView(generics.ListCreateAPIView):
    serializer_class = TableSerializer

    def get_queryset(self):
        return _tables_qs(_get_restaurant(self.request))

    def create(self, request, *args, **kwargs):
        restaurant = _get_restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        number = str(request.data.get('number', '')).strip()
        if not number:
            return Response({'detail': 'Masa nömrəsi vacibdir'}, status=400)
        if Table.objects.filter(restaurant=restaurant, number=number).exists():
            return Response(
                {'detail': f'Masa {number} artıq mövcuddur'},
                status=400,
            )

        zone = request.data.get('zone', 'zal')
        if zone not in dict(Table.ZONE_CHOICES):
            zone = 'zal'
        shape = request.data.get('shape', Table.SHAPE_ROUND)
        if shape not in dict(Table.SHAPE_CHOICES):
            shape = Table.SHAPE_ROUND

        try:
            capacity = max(1, int(request.data.get('capacity', 4)))
        except (TypeError, ValueError):
            capacity = 4

        width = 12 if shape == Table.SHAPE_ROUND else 14
        height = 12 if shape == Table.SHAPE_ROUND else 10

        existing = list(
            Table.objects.filter(restaurant=restaurant, zone=zone).values(
                'pos_x', 'pos_y', 'width', 'height'
            )
        )

        if request.data.get('pos_x') is not None and request.data.get('pos_y') is not None:
            pos_x = float(request.data['pos_x'])
            pos_y = float(request.data['pos_y'])
        else:
            pos_x, pos_y = find_free_position(existing, width, height)

        table = Table.objects.create(
            restaurant=restaurant,
            number=number,
            capacity=capacity,
            shape=shape,
            zone=zone,
            pos_x=pos_x,
            pos_y=pos_y,
            width=width,
            height=height,
        )
        table = _tables_qs(restaurant).get(pk=table.pk)
        return Response(TableSerializer(table).data, status=201)


class TableDetailView(APIView):
    def patch(self, request, pk):
        restaurant = _get_restaurant(request)
        table = Table.objects.filter(pk=pk, restaurant=restaurant).first()
        if not table:
            return Response({'detail': 'Masa tapılmadı'}, status=404)

        for field in (
            'number',
            'capacity',
            'shape',
            'zone',
            'pos_x',
            'pos_y',
            'width',
            'height',
            'rotation',
            'notes',
            'qr_enabled',
        ):
            if field in request.data:
                val = request.data[field]
                if field in ('pos_x', 'pos_y', 'width', 'height', 'rotation'):
                    try:
                        val = float(val)
                    except (TypeError, ValueError):
                        continue
                    if field in ('pos_x', 'pos_y'):
                        val = max(0.0, min(100.0, val))
                if field == 'capacity':
                    try:
                        val = int(val)
                    except (TypeError, ValueError):
                        continue
                setattr(table, field, val)
        table.save()
        table = _tables_qs(restaurant).get(pk=table.pk)
        return Response(TableSerializer(table).data)

    def delete(self, request, pk):
        restaurant = _get_restaurant(request)
        table = Table.objects.filter(pk=pk, restaurant=restaurant).first()
        if not table:
            return Response({'detail': 'Masa tapılmadı'}, status=404)
        active = table.orders.filter(status__in=ACTIVE_STATUSES).exists()
        if active:
            return Response(
                {'detail': 'Aktiv sifarişi olan masa silinə bilməz'},
                status=400,
            )
        table.delete()
        return Response(status=204)


class FloorPlanView(APIView):
    def get(self, request):
        restaurant = _get_restaurant(request)
        if not restaurant:
            return Response(
                {'detail': 'Restoran tapılmadı. Əvvəlcə seed_tables işlədin.'},
                status=404,
            )

        tables = list(_tables_qs(restaurant))
        elements = FloorElement.objects.filter(restaurant=restaurant)
        zones = [
            {'id': value, 'label': label}
            for value, label in Table.ZONE_CHOICES
        ]

        data = {
            'restaurant': {
                'id': restaurant.id,
                'name': restaurant.name,
                'slug': restaurant.slug,
            },
            'elements': elements,
            'tables': tables,
            'zones': zones,
        }
        return Response(FloorPlanSerializer(data).data)


class TableActionView(APIView):
    """Sürətli əməliyyatlar: hesab, ödəniş, boşalt, qeyd, split."""

    def post(self, request, pk):
        try:
            table = Table.objects.get(pk=pk)
        except Table.DoesNotExist:
            return Response({'detail': 'Masa tapılmadı'}, status=404)

        action = request.data.get('action')
        active_orders = table.orders.filter(status__in=ACTIVE_STATUSES)

        if action == 'request_bill':
            if not active_orders.exists():
                return Response({'detail': 'Aktiv sifariş yoxdur'}, status=400)
            table.awaiting_bill = True
            table.save(update_fields=['awaiting_bill'])
            create_notification(
                restaurant=table.restaurant,
                type='bill_request',
                message=f'Masa {table.number} hesab istəyir',
                link=f'/table',
                related_table=table,
                related_order=active_orders.first(),
            )

        elif action == 'call_waiter':
            create_notification(
                restaurant=table.restaurant,
                type='waiter_call',
                message=f'Masa {table.number} ofisiant çağırır',
                link='/table',
                related_table=table,
                related_order=active_orders.first() if active_orders.exists() else None,
            )

        elif action == 'take_payment':
            now = timezone.now()
            completed_ids = []
            for o in active_orders:
                o.status = 'completed'
                if not o.completed_at:
                    o.completed_at = now
                o.save(update_fields=['status', 'completed_at', 'updated_at'])
                completed_ids.append(o.id)
                if not o.payments.filter(status='paid').exists():
                    from payments.models import Payment

                    Payment.objects.create(
                        order=o,
                        restaurant=table.restaurant,
                        amount=o.total_amount,
                        currency=table.restaurant.currency or 'AZN',
                        method='cash',
                        gateway='',
                        status='paid',
                        paid_at=now,
                        raw_response={'via': 'table_take_payment'},
                    )
            table.awaiting_bill = False
            table.needs_cleaning = True
            table.split_bill = False
            table.save(
                update_fields=['awaiting_bill', 'needs_cleaning', 'split_bill']
            )
            slug = table.restaurant.slug if table.restaurant_id else 'surfues-resto'
            for oid in completed_ids:
                order = (
                    Order.objects.filter(pk=oid)
                    .select_related('table', 'served_by')
                    .prefetch_related('items__menu_item')
                    .first()
                )
                if order:
                    broadcast_order_event(
                        slug, 'order.completed', serialize_kanban_card(order)
                    )

        elif action == 'clear_table':
            now = timezone.now()
            completed_ids = []
            for o in active_orders:
                o.status = 'completed'
                if not o.completed_at:
                    o.completed_at = now
                o.save(update_fields=['status', 'completed_at', 'updated_at'])
                completed_ids.append(o.id)
            table.awaiting_bill = False
            table.needs_cleaning = False
            table.split_bill = False
            table.notes = ''
            table.save(
                update_fields=[
                    'awaiting_bill',
                    'needs_cleaning',
                    'split_bill',
                    'notes',
                ]
            )
            slug = table.restaurant.slug if table.restaurant_id else 'surfues-resto'
            for oid in completed_ids:
                order = (
                    Order.objects.filter(pk=oid)
                    .select_related('table', 'served_by')
                    .prefetch_related('items__menu_item')
                    .first()
                )
                if order:
                    broadcast_order_event(
                        slug, 'order.completed', serialize_kanban_card(order)
                    )

        elif action == 'mark_cleaned':
            table.needs_cleaning = False
            table.save(update_fields=['needs_cleaning'])

        elif action == 'add_order':
            Order.objects.create(
                restaurant=table.restaurant,
                table=table,
                source='waiter',
                status='received',
                total_amount=0,
                notes='Yeni sifariş',
            )
            table.needs_cleaning = False
            table.awaiting_bill = False
            table.save(update_fields=['needs_cleaning', 'awaiting_bill'])

        elif action == 'toggle_split_bill':
            table.split_bill = not table.split_bill
            table.save(update_fields=['split_bill'])

        elif action == 'update_notes':
            table.notes = request.data.get('notes', '')
            table.save(update_fields=['notes'])

        else:
            return Response({'detail': 'Naməlum əməliyyat'}, status=400)

        table = _tables_qs(table.restaurant).get(pk=table.pk)
        return Response(TableSerializer(table).data)


class ReservationCreateView(APIView):
    def post(self, request):
        table_id = request.data.get('table_id')
        try:
            table = Table.objects.select_related('restaurant').get(pk=table_id)
        except Table.DoesNotExist:
            return Response({'detail': 'Masa tapılmadı'}, status=404)

        reserved_for = request.data.get('reserved_for')
        if not reserved_for:
            return Response({'detail': 'reserved_for tələb olunur'}, status=400)

        reservation = Reservation.objects.create(
            restaurant=table.restaurant,
            table=table,
            guest_name=request.data.get('guest_name', 'Qonaq'),
            party_size=int(request.data.get('party_size', 2)),
            reserved_for=reserved_for,
            notes=request.data.get('notes', ''),
            status='pending',
        )
        table = _tables_qs(table.restaurant).get(pk=table.pk)
        return Response(
            {
                'reservation_id': reservation.id,
                'table': TableSerializer(table).data,
            },
            status=status.HTTP_201_CREATED,
        )
