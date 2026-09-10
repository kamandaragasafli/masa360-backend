from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from restaurants.models import Restaurant
from warehouse.models import IngredientBatch, IngredientCategory, RawIngredient


class Command(BaseCommand):
    help = 'Demo anbar xammalları və partiyalar'

    def handle(self, *args, **options):
        restaurant = (
            Restaurant.objects.filter(slug='surfues-resto').first()
            or Restaurant.objects.first()
        )
        if not restaurant:
            self.stderr.write('Restoran yoxdur')
            return

        cats = {
            'Ət': None,
            'Tərəvəz': None,
            'Süd məhsulları': None,
            'Yağlar': None,
            'Ədviyyat': None,
        }
        for i, name in enumerate(cats):
            cat, _ = IngredientCategory.objects.get_or_create(
                restaurant=restaurant,
                name=name,
                defaults={'order': i},
            )
            cats[name] = cat

        today = timezone.localdate()
        samples = [
            # name, cat, unit, min, batches[(qty, days_left, supplier)]
            (
                'Mal əti',
                'Ət',
                'kg',
                '2',
                [
                    (Decimal('2.1'), 1, 'Ət bazarı'),
                    (Decimal('2.1'), 5, 'Ət bazarı'),
                ],
            ),
            (
                'Pomidor',
                'Tərəvəz',
                'kg',
                '3',
                [(Decimal('1.8'), 8, 'Tərəvəz topdan')],
            ),
            (
                'Soğan',
                'Tərəvəz',
                'kg',
                '1',
                [(Decimal('4.5'), 12, 'Tərəvəz topdan')],
            ),
            (
                'Yağ',
                'Yağlar',
                'l',
                '1',
                [(Decimal('2.0'), 30, 'Metro')],
            ),
            (
                'Ayran',
                'Süd məhsulları',
                'l',
                '2',
                [(Decimal('0.8'), 0, 'Süd evi')],
            ),
            (
                'Duz',
                'Ədviyyat',
                'kg',
                '0.5',
                [(Decimal('5.0'), 90, 'Metro')],
            ),
        ]

        for name, cat_name, unit, min_stock, batches in samples:
            ing, _ = RawIngredient.objects.update_or_create(
                restaurant=restaurant,
                name=name,
                defaults={
                    'category': cats[cat_name],
                    'unit': unit,
                    'min_stock': Decimal(min_stock),
                    'is_active': True,
                },
            )
            # Mövcud partiyaları təmizləmə — yalnız boşdursa əlavə et
            if not ing.batches.exists():
                for qty, days, supplier in batches:
                    IngredientBatch.objects.create(
                        ingredient=ing,
                        quantity=qty,
                        remaining_quantity=qty,
                        expiry_date=today + timedelta(days=days),
                        supplier=supplier,
                    )

        self.stdout.write(self.style.SUCCESS('Warehouse demo data ready'))
