from datetime import time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from menu.models import Category, MenuItem
from orders.models import Order, OrderItem
from restaurants.models import Restaurant
from tables.models import FloorElement, Reservation, Table


class Command(BaseCommand):
    help = 'Demo restaurant floor plan with reservations'

    def handle(self, *args, **options):
        restaurant, created = Restaurant.objects.get_or_create(
            slug='surfues-resto',
            defaults={
                'name': '',
                'address': 'Baki, Nizami kuc. 1',
                'phone': '+994501234567',
                'is_active': True,
                'opening_time': time(10, 0),
                'closing_time': time(23, 0),
            },
        )
        self.stdout.write(
            f"Restaurant {'created' if created else 'exists'}: {restaurant.slug}"
        )

        category, _ = Category.objects.get_or_create(
            restaurant=restaurant,
            name='Esas yemekler',
            defaults={'order': 1},
        )

        def item(name, price):
            obj, _ = MenuItem.objects.get_or_create(
                restaurant=restaurant,
                name=name,
                defaults={
                    'category': category,
                    'price': Decimal(price),
                    'is_available': True,
                },
            )
            return obj

        kabab = item('Kabab', '15.00')
        salat = item('Salat', '8.00')
        cay = item('Cay', '2.50')
        pizza = item('Pizza', '12.50')
        desert = item('Desert', '7.00')

        Table.objects.filter(restaurant=restaurant).delete()
        FloorElement.objects.filter(restaurant=restaurant).delete()
        Reservation.objects.filter(restaurant=restaurant).delete()

        elements = [
            ('cashier', 'KASSA', 8, 10, 14, 14),
            ('wash', 'ƏL YUMA', 8, 32, 12, 8),
            ('restroom', 'TUALET', 8, 44, 12, 8),
            ('exit', 'ÇIXIŞ', 38, 4, 10, 5),
            ('entry', 'GİRİŞ', 52, 4, 10, 5),
            ('stairs', 'PİLLƏKƏN', 78, 6, 16, 10),
            ('room', 'VIP OTAQ', 88, 88, 14, 12),
        ]
        for etype, label, x, y, w, h in elements:
            FloorElement.objects.create(
                restaurant=restaurant,
                element_type=etype,
                label=label,
                pos_x=x,
                pos_y=y,
                width=w,
                height=h,
            )

        tables_by_number = {}

        round_zal = [
            ('1', 28, 22),
            ('2', 42, 22),
            ('3', 56, 22),
            ('4', 70, 22),
            ('5', 28, 42),
            ('6', 42, 42),
            ('7', 56, 42),
            ('8', 70, 42),
        ]
        for number, x, y in round_zal:
            t = Table.objects.create(
                restaurant=restaurant,
                number=number,
                capacity=6,
                shape=Table.SHAPE_ROUND,
                zone='zal',
                pos_x=x,
                pos_y=y,
                width=12,
                height=14,
            )
            tables_by_number[number] = t

        for number, x, y in [('12', 28, 62), ('13', 42, 62)]:
            t = Table.objects.create(
                restaurant=restaurant,
                number=number,
                capacity=4,
                shape=Table.SHAPE_ROUND,
                zone='zal',
                pos_x=x,
                pos_y=y,
                width=10,
                height=12,
            )
            tables_by_number[number] = t

        for number, x, y, w, h, cap in [
            ('11', 18, 72, 10, 14, 12),
            ('10', 32, 72, 10, 14, 12),
            ('9', 55, 74, 26, 9, 18),
        ]:
            t = Table.objects.create(
                restaurant=restaurant,
                number=number,
                capacity=cap,
                shape=Table.SHAPE_RECT,
                zone='zal',
                pos_x=x,
                pos_y=y,
                width=w,
                height=h,
            )
            tables_by_number[number] = t

        # Terras + VIP nümunə masaları (zona tab üçün)
        t14 = Table.objects.create(
            restaurant=restaurant,
            number='14',
            capacity=4,
            shape=Table.SHAPE_ROUND,
            zone='terras',
            pos_x=35,
            pos_y=40,
            width=12,
            height=14,
        )
        tables_by_number['14'] = t14
        t15 = Table.objects.create(
            restaurant=restaurant,
            number='15',
            capacity=6,
            shape=Table.SHAPE_ROUND,
            zone='vip',
            pos_x=50,
            pos_y=45,
            width=14,
            height=16,
            notes='Dogum gunu — tort goturulsun',
        )
        tables_by_number['15'] = t15

        Order.objects.filter(
            restaurant=restaurant,
            status__in=['received', 'preparing', 'ready', 'delivering'],
        ).update(status='completed')

        demo_orders = [
            (
                '2',
                'received',
                Decimal('33.00'),
                '',
                [(kabab, 2), (salat, 1), (cay, 1)],
                False,
                False,
                'Allergiya: fındıq',
            ),
            (
                '3',
                'preparing',
                Decimal('40.50'),
                '2 nefer',
                [(kabab, 2), (salat, 1), (cay, 1)],
                False,
                False,
                '',
            ),
            (
                '5',
                'ready',
                Decimal('27.50'),
                '',
                [(pizza, 1), (salat, 1), (cay, 2)],
                True,
                False,
                '',
            ),
            (
                '6',
                'delivering',
                Decimal('34.50'),
                'Desert',
                [(pizza, 2), (desert, 1)],
                False,
                False,
                '',
            ),
            (
                '10',
                'preparing',
                Decimal('67.20'),
                'VIP',
                [(kabab, 3), (salat, 2), (cay, 3)],
                False,
                False,
                '',
            ),
            (
                '13',
                'received',
                Decimal('19.90'),
                '',
                [(pizza, 1), (cay, 1)],
                False,
                False,
                '',
            ),
        ]

        for (
            number,
            st,
            amount,
            notes,
            items,
            awaiting,
            cleaning,
            table_notes,
        ) in demo_orders:
            table = tables_by_number[number]
            order = Order.objects.create(
                restaurant=restaurant,
                table=table,
                source='waiter',
                status=st,
                total_amount=amount,
                notes=notes,
            )
            for menu_item, qty in items:
                OrderItem.objects.create(
                    order=order,
                    menu_item=menu_item,
                    quantity=qty,
                    unit_price=menu_item.price,
                )
            table.awaiting_bill = awaiting
            table.needs_cleaning = cleaning
            table.notes = table_notes
            table.save(update_fields=['awaiting_bill', 'needs_cleaning', 'notes'])

        # Təmizlik nümunəsi
        tables_by_number['8'].needs_cleaning = True
        tables_by_number['8'].save(update_fields=['needs_cleaning'])

        now = timezone.now()
        Reservation.objects.create(
            restaurant=restaurant,
            table=tables_by_number['1'],
            guest_name='Aliyev',
            party_size=4,
            reserved_for=now.replace(hour=19, minute=0, second=0, microsecond=0)
            if now.hour < 19
            else now + timedelta(hours=2),
            notes='Pəncərə yanı',
        )
        Reservation.objects.create(
            restaurant=restaurant,
            table=tables_by_number['4'],
            guest_name='Mammadova',
            party_size=6,
            reserved_for=now + timedelta(hours=3),
        )
        Reservation.objects.create(
            restaurant=restaurant,
            table=tables_by_number['14'],
            guest_name='Terras qrupu',
            party_size=4,
            reserved_for=now + timedelta(hours=1),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Ready: {Table.objects.filter(restaurant=restaurant).count()} tables, '
                f'{Reservation.objects.filter(restaurant=restaurant).count()} reservations'
            )
        )
