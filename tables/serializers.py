from django.utils import timezone
from rest_framework import serializers

from .models import FloorElement, Reservation, Table

ACTIVE_STATUSES = ('received', 'preparing', 'ready', 'delivering')

STATUS_LABELS = {
    'empty': 'Boş',
    'occupied': 'Dolu',
    'reserved': 'Rezerv edilib',
    'cleaning': 'Təmizlənməlidir',
    'awaiting_bill': 'Hesab gözləyir',
}


class FloorElementSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source='get_element_type_display', read_only=True)

    class Meta:
        model = FloorElement
        fields = (
            'id',
            'element_type',
            'type_label',
            'label',
            'pos_x',
            'pos_y',
            'width',
            'height',
        )


class ReservationSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Reservation
        fields = (
            'id',
            'guest_name',
            'party_size',
            'reserved_for',
            'status',
            'status_label',
            'notes',
        )


class TableSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    has_order = serializers.SerializerMethodField()
    order = serializers.SerializerMethodField()
    reservation = serializers.SerializerMethodField()
    occupied_since = serializers.SerializerMethodField()
    occupied_minutes = serializers.SerializerMethodField()
    shape_label = serializers.CharField(source='get_shape_display', read_only=True)
    zone_label = serializers.CharField(source='get_zone_display', read_only=True)

    class Meta:
        model = Table
        fields = (
            'id',
            'number',
            'capacity',
            'shape',
            'shape_label',
            'zone',
            'zone_label',
            'pos_x',
            'pos_y',
            'width',
            'height',
            'rotation',
            'notes',
            'needs_cleaning',
            'awaiting_bill',
            'split_bill',
            'status',
            'status_label',
            'has_order',
            'order',
            'reservation',
            'occupied_since',
            'occupied_minutes',
            'qr_code',
            'qr_enabled',
        )

    def _active_order(self, obj):
        if hasattr(obj, '_active_order_cache'):
            return obj._active_order_cache
        # Prefetch varsa ondan istifadə et
        if (
            hasattr(obj, '_prefetched_objects_cache')
            and 'orders' in obj._prefetched_objects_cache
        ):
            orders = [
                o for o in obj.orders.all() if o.status in ACTIVE_STATUSES
            ]
            order = orders[0] if orders else None
        else:
            order = (
                obj.orders.filter(status__in=ACTIVE_STATUSES)
                .prefetch_related('items__menu_item')
                .order_by('-created_at')
                .first()
            )
        obj._active_order_cache = order
        return order

    def _upcoming_reservation(self, obj):
        if hasattr(obj, '_reservation_cache'):
            return obj._reservation_cache
        now = timezone.now()
        if (
            hasattr(obj, '_prefetched_objects_cache')
            and 'reservations' in obj._prefetched_objects_cache
        ):
            upcoming = [
                r
                for r in obj.reservations.all()
                if r.status == 'pending' and r.reserved_for >= now
            ]
            reservation = sorted(upcoming, key=lambda r: r.reserved_for)[0] if upcoming else None
        else:
            reservation = (
                obj.reservations.filter(status='pending', reserved_for__gte=now)
                .order_by('reserved_for')
                .first()
            )
        obj._reservation_cache = reservation
        return reservation

    def get_has_order(self, obj):
        return self._active_order(obj) is not None

    def get_status(self, obj):
        if obj.needs_cleaning:
            return 'cleaning'
        if obj.awaiting_bill and self._active_order(obj):
            return 'awaiting_bill'
        if self._active_order(obj):
            return 'occupied'
        if self._upcoming_reservation(obj):
            return 'reserved'
        return 'empty'

    def get_status_label(self, obj):
        return STATUS_LABELS.get(self.get_status(obj), self.get_status(obj))

    def get_occupied_since(self, obj):
        order = self._active_order(obj)
        return order.created_at.isoformat() if order else None

    def get_occupied_minutes(self, obj):
        order = self._active_order(obj)
        if not order:
            return None
        delta = timezone.now() - order.created_at
        return max(0, int(delta.total_seconds() // 60))

    def get_reservation(self, obj):
        reservation = self._upcoming_reservation(obj)
        if not reservation:
            return None
        return ReservationSerializer(reservation).data

    def get_order(self, obj):
        order = self._active_order(obj)
        if not order:
            return None
        items = []
        for item in order.items.all():
            items.append(
                {
                    'id': item.id,
                    'name': item.menu_item.name,
                    'quantity': item.quantity,
                    'unit_price': str(item.unit_price),
                    'line_total': str(item.unit_price * item.quantity),
                    'special_instructions': item.special_instructions,
                }
            )
        items_count = sum(i['quantity'] for i in items)
        return {
            'id': order.id,
            'status': order.status,
            'status_label': order.get_status_display(),
            'source': order.source,
            'source_label': order.get_source_display(),
            'total_amount': str(order.total_amount),
            'items_count': items_count,
            'items': items,
            'notes': order.notes,
            'created_at': order.created_at.isoformat(),
        }


class FloorPlanSerializer(serializers.Serializer):
    restaurant = serializers.DictField()
    elements = FloorElementSerializer(many=True)
    tables = TableSerializer(many=True)
    zones = serializers.ListField()
