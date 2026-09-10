from django.db.models import Count
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from menu.models import MenuItem
from restaurants.tenancy import resolve_restaurant
from tables.models import Table

from notifications.services import create_notification
from .models import Order, OrderItem, PrintJob
from .realtime import broadcast_order_event
from .kot import enqueue_kitchen_tickets, enqueue_print_job


KITCHEN_STATUSES = ('received', 'preparing', 'ready')
STATUS_FLOW = {
    'received': 'preparing',
    'preparing': 'ready',
}


def _restaurant(request):
    return resolve_restaurant(request)


def _slug_for(restaurant):
    return restaurant.slug if restaurant else ''


def _serialize_order(order):
    return OrderSerializer(order).data


class OrderItemLineSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=99)
    special_instructions = serializers.CharField(
        required=False, allow_blank=True, default=''
    )


class OrderCreateSerializer(serializers.Serializer):
    table_id = serializers.IntegerField(required=False, allow_null=True)
    takeaway = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    source = serializers.ChoiceField(
        choices=[c[0] for c in Order.SOURCE_CHOICES],
        default='waiter',
    )
    items = OrderItemLineSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError('Səbət boşdur')
        return value


class OrderItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='menu_item.name', read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            'id',
            'menu_item',
            'name',
            'quantity',
            'unit_price',
            'special_instructions',
            'line_total',
        )

    def get_line_total(self, obj):
        return obj.line_total


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_label = serializers.CharField(
        source='get_status_display', read_only=True
    )
    source_label = serializers.CharField(
        source='get_source_display', read_only=True
    )
    table_number = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    age_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'id',
            'table',
            'table_number',
            'title',
            'source',
            'source_label',
            'order_type',
            'status',
            'status_label',
            'total_amount',
            'notes',
            'delivery_address',
            'customer_name',
            'customer_phone',
            'delivery_fee',
            'items',
            'created_at',
            'updated_at',
            'age_seconds',
        )

    def get_table_number(self, obj):
        return obj.table.number if obj.table_id else None

    def get_title(self, obj):
        if getattr(obj, 'order_type', None) == 'delivery' or (
            not obj.table_id and obj.source in ('mobile_app', 'online')
        ):
            return f'Çatdırılma #{obj.pk}'
        if obj.table_id and obj.table:
            return f'Masa {obj.table.number}'
        return f'Al-apar #{obj.pk}'

    def get_age_seconds(self, obj):
        return max(0, int((timezone.now() - obj.created_at).total_seconds()))


class OrderCreateView(APIView):
    @transaction.atomic
    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        ser = OrderCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        takeaway = data.get('takeaway') or data.get('table_id') in (None, '')
        table = None
        if not takeaway and data.get('table_id'):
            table = Table.objects.filter(
                pk=data['table_id'], restaurant=restaurant
            ).first()
            if not table:
                return Response({'detail': 'Masa tapılmadı'}, status=404)

        item_ids = [line['menu_item_id'] for line in data['items']]
        menu_map = {
            m.id: m
            for m in MenuItem.objects.filter(
                restaurant=restaurant, pk__in=item_ids, is_active=True
            )
        }

        lines = []
        total = Decimal('0.00')
        for line in data['items']:
            menu_item = menu_map.get(line['menu_item_id'])
            if not menu_item:
                return Response(
                    {'detail': f'Məhsul tapılmadı: {line["menu_item_id"]}'},
                    status=400,
                )
            if not menu_item.is_available:
                return Response(
                    {'detail': f'“{menu_item.name}” bitib'},
                    status=400,
                )
            qty = line['quantity']
            unit = Decimal(menu_item.price)
            total += unit * qty
            lines.append(
                (
                    menu_item,
                    qty,
                    unit,
                    (line.get('special_instructions') or '')[:255],
                )
            )

        order_type = 'dine_in' if table else 'takeaway'
        order = Order.objects.create(
            restaurant=restaurant,
            table=table,
            source=data.get('source', 'waiter'),
            order_type=order_type,
            status='received',
            total_amount=total,
            notes=(data.get('notes') or '').strip(),
        )

        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=qty,
                    unit_price=unit,
                    special_instructions=note,
                )
                for menu_item, qty, unit, note in lines
            ]
        )

        if table:
            table.needs_cleaning = False
            table.awaiting_bill = False
            table.save(update_fields=['needs_cleaning', 'awaiting_bill'])

        order = (
            Order.objects.filter(pk=order.pk)
            .select_related('table', 'restaurant')
            .prefetch_related('items__menu_item')
            .first()
        )
        payload = _serialize_order(order)
        print_jobs = []
        # Kanban / KDS — həmişə real-time (printer-only rejimdə də lövhə yenilənsin)
        broadcast_order_event(
            _slug_for(restaurant), 'order.created', payload
        )
        if restaurant.uses_printer:
            print_jobs = [
                {'id': j.id, 'printer': j.printer_id, 'status': j.status}
                for j in enqueue_kitchen_tickets(order)
            ]

        table_label = (
            f'Masa {order.table.number}' if order.table_id else f'#{order.id}'
        )
        create_notification(
            restaurant=restaurant,
            type='new_order',
            message=f'{table_label} — yeni sifariş mətbəxə düşdü',
            link='/kitchen',
            related_order=order,
            related_table=order.table,
        )
        if order.source == 'qr':
            create_notification(
                restaurant=restaurant,
                type='new_qr_order',
                message=f'{table_label} — QR sifarişi təsdiq gözləyir',
                link=f'/order?table={order.table_id}' if order.table_id else '/order',
                related_order=order,
                related_table=order.table,
            )

        response = {**payload, 'print_jobs': print_jobs}
        return Response(response, status=201)


class KitchenOrderListView(APIView):
    """Aktiv mətbəx sifarişləri: received / preparing / ready."""

    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        status = request.query_params.get('status')
        qs = (
            Order.objects.filter(
                restaurant=restaurant, status__in=KITCHEN_STATUSES
            )
            .annotate(items_count=Count('items'))
            .filter(items_count__gt=0)
            .select_related('table')
            .prefetch_related('items__menu_item')
            .order_by('created_at')
        )
        if status in KITCHEN_STATUSES:
            qs = qs.filter(status=status)

        return Response(OrderSerializer(qs, many=True).data)


class OrderAdvanceView(APIView):
    """
    Tək toxunuşla status irəliləyişi:
    received → preparing → ready
    """

    @transaction.atomic
    def post(self, request, pk):
        restaurant = _restaurant(request)
        order = (
            Order.objects.filter(pk=pk)
            .select_related('table', 'restaurant')
            .prefetch_related('items__menu_item')
            .first()
        )
        if not order:
            return Response({'detail': 'Sifariş tapılmadı'}, status=404)
        if restaurant and order.restaurant_id != restaurant.id:
            return Response({'detail': 'Sifariş tapılmadı'}, status=404)

        nxt = STATUS_FLOW.get(order.status)
        if not nxt:
            return Response(
                {'detail': 'Bu sifariş artıq irəlilədilə bilməz'},
                status=400,
            )

        order.status = nxt
        order.apply_status_timestamp(nxt)
        update_fields = ['status', 'updated_at']
        if nxt == 'preparing':
            update_fields.append('preparing_at')
        elif nxt == 'ready':
            update_fields.append('ready_at')
        order.save(update_fields=update_fields)

        order = (
            Order.objects.filter(pk=order.pk)
            .select_related('table', 'restaurant')
            .prefetch_related('items__menu_item')
            .first()
        )
        payload = _serialize_order(order)
        event = 'order.preparing' if nxt == 'preparing' else 'order.ready'
        broadcast_order_event(_slug_for(order.restaurant), event, payload)
        if nxt == 'preparing':
            # FIFO stok azalması — resept varsa
            try:
                from warehouse.services import deduct_stock_for_order

                deduct_stock_for_order(order)
            except Exception:
                import logging

                logging.getLogger(__name__).exception(
                    'stock deduct failed order=%s', order.id
                )
        if nxt == 'ready':
            from delivery.services import assign_courier, is_delivery_order

            delivery = is_delivery_order(order)
            if delivery:
                create_notification(
                    restaurant=order.restaurant,
                    type='order_ready',
                    message=(
                        f'Çatdırılma #{order.id} hazırdır — kuryerə göndərildi'
                    ),
                    link='/board',
                    related_order=order,
                    related_table=None,
                )
                try:
                    assign_courier(
                        order,
                        dropoff_address=(
                            getattr(order, 'delivery_address', '')
                            or (order.notes or '')[:200]
                        ),
                        customer_phone=(
                            getattr(order, 'customer_phone', '')
                            or order.guest_phone
                            or ''
                        ),
                    )
                except Exception:
                    import logging

                    logging.getLogger(__name__).exception(
                        'delivery assign failed order=%s', order.id
                    )
                order.refresh_from_db()
                payload = _serialize_order(
                    Order.objects.filter(pk=order.pk)
                    .select_related('table', 'restaurant')
                    .prefetch_related('items__menu_item')
                    .first()
                )
                if order.status == 'delivering':
                    broadcast_order_event(
                        _slug_for(order.restaurant),
                        'order.delivering',
                        payload,
                    )
            else:
                table_label = (
                    f'Masa {order.table.number}'
                    if order.table_id
                    else f'Sifariş #{order.id}'
                )
                create_notification(
                    restaurant=order.restaurant,
                    type='order_ready',
                    message=f'{table_label} hazırdır — götürün',
                    link=(
                        f'/order?table={order.table_id}'
                        if order.table_id
                        else '/order'
                    ),
                    related_order=order,
                    related_table=order.table,
                )
        return Response(payload)


class PrintJobSerializer(serializers.ModelSerializer):
    printer_name = serializers.CharField(source='printer.name', read_only=True)
    order_title = serializers.SerializerMethodField()

    class Meta:
        model = PrintJob
        fields = (
            'id',
            'order',
            'order_title',
            'printer',
            'printer_name',
            'status',
            'error_message',
            'payload',
            'is_test',
            'created_at',
            'updated_at',
        )

    def get_order_title(self, obj):
        if obj.payload and obj.payload.get('title'):
            return obj.payload['title']
        if obj.order_id:
            return f'#{obj.order_id}'
        return 'Test'


class PrintJobListView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        qs = (
            PrintJob.objects.filter(printer__restaurant=restaurant)
            .select_related('printer', 'order')
            .order_by('-created_at')[:50]
        )
        failed_only = request.query_params.get('failed')
        if failed_only in ('1', 'true', 'True'):
            qs = qs.filter(status='failed')
        return Response(PrintJobSerializer(qs, many=True).data)


class PrintJobRetryView(APIView):
    def post(self, request, pk):
        restaurant = _restaurant(request)
        job = (
            PrintJob.objects.select_related('printer')
            .filter(pk=pk)
            .first()
        )
        if not job:
            return Response({'detail': 'Çap işi tapılmadı'}, status=404)
        if restaurant and job.printer.restaurant_id != restaurant.id:
            return Response({'detail': 'Çap işi tapılmadı'}, status=404)

        job.status = 'pending'
        job.error_message = ''
        job.save(update_fields=['status', 'error_message', 'updated_at'])
        enqueue_print_job(job.id)
        job.refresh_from_db()
        return Response(PrintJobSerializer(job).data)
