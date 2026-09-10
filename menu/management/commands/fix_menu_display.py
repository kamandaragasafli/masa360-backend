from django.core.management.base import BaseCommand

from menu.models import Category, MenuItem
from restaurants.models import Restaurant


# Unsplash food photos — hamısı 4:3 crop
IMAGES = {
    'Humus': 'https://images.unsplash.com/photo-1625944230946-1e3993906964?w=800&h=600&fit=crop&crop=entropy',
    'Cacık': 'https://images.unsplash.com/photo-1607532941433-304659e8198a?w=800&h=600&fit=crop&crop=entropy',
    'Kabab': 'https://images.unsplash.com/photo-1603360946369-dc9bb6258143?w=800&h=600&fit=crop&crop=entropy',
    'Pizza': 'https://images.unsplash.com/photo-1513104890138-7c749659a591?w=800&h=600&fit=crop&crop=entropy',
    'Sezar salatı': 'https://images.unsplash.com/photo-1546793665-c74683f339c1?w=800&h=600&fit=crop&crop=entropy',
    'Toyuq qovurma': 'https://images.unsplash.com/photo-1598103442097-8b74394b95c6?w=800&h=600&fit=crop&crop=entropy',
    'Mərci şorbası': 'https://images.unsplash.com/photo-1547592166-23ac45744acd?w=800&h=600&fit=crop&crop=entropy',
    'Paxlava': 'https://images.unsplash.com/photo-1599599810769-bcde5a160d32?w=800&h=600&fit=crop&crop=entropy',
    'Dondurma': 'https://images.unsplash.com/photo-1497034825429-c343d7c6a68f?w=800&h=600&fit=crop&crop=entropy',
    'Çay': 'https://images.unsplash.com/photo-1571934811356-5cc061b6821f?w=800&h=600&fit=crop&crop=entropy',
    'Limonad': 'https://images.unsplash.com/photo-1621506289937-a8e4df240d0b?w=800&h=600&fit=crop&crop=entropy',
    'Cola': 'https://images.unsplash.com/photo-1554866585-cd94860890b7?w=800&h=600&fit=crop&crop=entropy',
    'Pizza Margherita': 'https://images.unsplash.com/photo-1574071318508-1cdbab80d002?w=800&h=600&fit=crop&crop=entropy',
    'Salat': 'https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&h=600&fit=crop&crop=entropy',
    'Desert': 'https://images.unsplash.com/photo-1488477181946-6428a0291777?w=800&h=600&fit=crop&crop=entropy',
}

ITEM_RENAMES = {
    'Cacik': 'Cacık',
    'Cay': 'Çay',
    'Sezar salati': 'Sezar salatı',
    'Mercimek': 'Mərci şorbası',
    'Baklava': 'Paxlava',
    'Humus': 'Humus',
    'Kabab': 'Kabab',
    'Pizza': 'Pizza',
    'Toyuq qovurma': 'Toyuq qovurma',
    'Dondurma': 'Dondurma',
    'Limonad': 'Limonad',
    'Cola': 'Cola',
}

CAT_RENAMES = {
    'Baslanğıclar': 'Başlanğıclar',
    'Baslangiclar': 'Başlanğıclar',
    'Esas yemekler': 'Əsas yeməklər',
    'Sorbalar': 'Şorbalar',
    'Desertler': 'Desertlər',
    'Ickiler': 'İçkilər',
    'Movsum menyusu': 'Mövsüm menyusu',
}


class Command(BaseCommand):
    help = 'Fix Azerbaijani category/item names and set Unsplash images'

    def handle(self, *args, **options):
        restaurant = Restaurant.objects.filter(slug='surfues-resto').first()
        if not restaurant:
            self.stdout.write('No restaurant')
            return

        for cat in Category.objects.filter(restaurant=restaurant):
            new_name = CAT_RENAMES.get(cat.name)
            if new_name and new_name != cat.name:
                # merge if target exists
                existing = Category.objects.filter(
                    restaurant=restaurant, name=new_name
                ).exclude(pk=cat.pk).first()
                if existing:
                    MenuItem.objects.filter(category=cat).update(category=existing)
                    cat.delete()
                else:
                    cat.name = new_name
                    cat.save(update_fields=['name'])

        # Ensure canonical categories exist with correct order
        wanted = [
            ('Başlanğıclar', 0),
            ('Əsas yeməklər', 1),
            ('Şorbalar', 2),
            ('Desertlər', 3),
            ('İçkilər', 4),
            ('Mövsüm menyusu', 5),
        ]
        for name, order in wanted:
            cat, _ = Category.objects.get_or_create(
                restaurant=restaurant,
                name=name,
                defaults={'order': order, 'is_active': name != 'Mövsüm menyusu'},
            )
            cat.order = order
            if name == 'Mövsüm menyusu':
                cat.is_active = False
            cat.save()

        for item in MenuItem.objects.filter(restaurant=restaurant):
            if item.name in ITEM_RENAMES:
                item.name = ITEM_RENAMES[item.name]
            url = IMAGES.get(item.name)
            if url:
                item.image_url = url
            item.save()

        # Write report without console unicode issues
        report = []
        for c in Category.objects.filter(restaurant=restaurant).order_by('order'):
            report.append(f'CAT {c.order}: {c.name}')
        for i in MenuItem.objects.filter(restaurant=restaurant).order_by('name'):
            report.append(f'ITEM {i.name} | img={bool(i.image_url)}')
        path = 'menu_fix_report.txt'
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))
        self.stdout.write(self.style.SUCCESS(f'Done -> {path}'))
