from datetime import time
from decimal import Decimal

from django.core.management.base import BaseCommand

from menu.models import Category, MenuItem, Modifier, ModifierGroup
from restaurants.models import Restaurant


class Command(BaseCommand):
    help = 'Seed menu categories and items'

    def handle(self, *args, **options):
        restaurant, _ = Restaurant.objects.get_or_create(
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

        # Köhnə menyunu silmə — OrderItem PROTECT ola bilər; kateqoriyaları yenilə
        categories_data = [
            ('Başlanğıclar', 0),
            ('Əsas yeməklər', 1),
            ('Şorbalar', 2),
            ('Desertlər', 3),
            ('İçkilər', 4),
        ]

        cats = {}
        for name, order in categories_data:
            cat, _ = Category.objects.get_or_create(
                restaurant=restaurant,
                name=name,
                defaults={'order': order, 'is_active': True},
            )
            cat.order = order
            cat.is_active = True
            cat.save()
            cats[name] = cat

        # Mövsümi gizlədilmiş nümunə
        seasonal, _ = Category.objects.get_or_create(
            restaurant=restaurant,
            name='Mövsüm menyusu',
            defaults={'order': 5, 'is_active': False},
        )

        items_data = [
            ('Başlanğıclar', 'Humus', 'Zeytun yağı ilə', '6.50', 10, True, True, True, False, 0),
            ('Başlanğıclar', 'Cacık', '', '5.00', 8, True, True, False, False, 0),
            ('Əsas yeməklər', 'Kabab', 'Manqalda', '15.00', 25, True, True, False, False, 2),
            ('Əsas yeməklər', 'Pizza', 'Klassik', '12.50', 20, True, True, False, False, 0),
            ('Əsas yeməklər', 'Sezar salatı', '', '8.00', 12, False, True, False, False, 0),
            ('Əsas yeməklər', 'Toyuq qovurma', '', '14.00', 22, True, True, False, False, 1),
            ('Şorbalar', 'Mərci şorbası', '', '4.50', 15, True, True, True, True, 0),
            ('Desertlər', 'Paxlava', '', '7.00', 5, True, True, False, False, 0),
            ('Desertlər', 'Dondurma', '3 top', '5.50', 3, True, False, False, False, 0),
            ('İçkilər', 'Çay', '', '2.50', 5, True, True, True, True, 0),
            ('İçkilər', 'Limonad', '', '4.00', 5, True, True, True, True, 0),
            ('İçkilər', 'Cola', '', '3.50', 2, True, True, False, False, 0),
        ]

        for (
            cat_name,
            name,
            desc,
            price,
            prep,
            available,
            active,
            vegan,
            gluten_free,
            spicy,
        ) in items_data:
            item, created = MenuItem.objects.get_or_create(
                restaurant=restaurant,
                name=name,
                defaults={
                    'category': cats[cat_name],
                    'description': desc,
                    'price': Decimal(price),
                    'prep_time_minutes': prep,
                    'is_available': available,
                    'is_active': active,
                    'is_vegan': vegan,
                    'is_gluten_free': gluten_free,
                    'spicy_level': spicy,
                },
            )
            if not created:
                item.category = cats[cat_name]
                item.description = desc
                item.price = Decimal(price)
                item.prep_time_minutes = prep
                item.is_available = available
                item.is_active = active
                item.is_vegan = vegan
                item.is_gluten_free = gluten_free
                item.spicy_level = spicy
                item.save()

        # Unsplash images
        from menu.management.commands.fix_menu_display import IMAGES
        for item in MenuItem.objects.filter(restaurant=restaurant):
            url = IMAGES.get(item.name)
            if url:
                item.image_url = url
                item.save(update_fields=['image_url'])

        # Kabab üçün modifikatorlar
        kabab = MenuItem.objects.filter(restaurant=restaurant, name='Kabab').first()
        if kabab:
            kabab.modifier_groups.all().delete()
            meat = ModifierGroup.objects.create(
                menu_item=kabab,
                name='Ət seçimi',
                is_required=True,
                min_select=1,
                max_select=1,
                order=0,
            )
            Modifier.objects.create(group=meat, name='Mal əti', extra_price=0, order=0)
            Modifier.objects.create(group=meat, name='Toyuq', extra_price=0, order=1)
            Modifier.objects.create(group=meat, name='Qarışıq', extra_price=2, order=2)

            extras = ModifierGroup.objects.create(
                menu_item=kabab,
                name='Əlavələr',
                is_required=False,
                min_select=0,
                max_select=3,
                order=1,
            )
            Modifier.objects.create(group=extras, name='Əlavə pendir', extra_price=2, order=0)
            Modifier.objects.create(group=extras, name='Əlavə sous', extra_price=1, order=1)

        # Pizza üçün modifikatorlar
        pizza = MenuItem.objects.filter(restaurant=restaurant, name='Pizza').first()
        if pizza:
            pizza.modifier_groups.all().delete()
            size = ModifierGroup.objects.create(
                menu_item=pizza,
                name='Ölçü',
                is_required=True,
                min_select=1,
                max_select=1,
                order=0,
            )
            Modifier.objects.create(group=size, name='Kiçik', extra_price=0, order=0)
            Modifier.objects.create(group=size, name='Orta', extra_price=2, order=1)
            Modifier.objects.create(group=size, name='Böyük', extra_price=4, order=2)

            toppings = ModifierGroup.objects.create(
                menu_item=pizza,
                name='Əlavələr',
                is_required=False,
                min_select=0,
                max_select=4,
                order=1,
            )
            Modifier.objects.create(group=toppings, name='Əlavə pendir', extra_price=2, order=0)
            Modifier.objects.create(group=toppings, name='Göbələk', extra_price=1.5, order=1)
            Modifier.objects.create(group=toppings, name='Zeytun', extra_price=1, order=2)

        self.stdout.write(
            self.style.SUCCESS(
                f'Menu ready: {Category.objects.filter(restaurant=restaurant).count()} cats, '
                f'{MenuItem.objects.filter(restaurant=restaurant).count()} items'
            )
        )
