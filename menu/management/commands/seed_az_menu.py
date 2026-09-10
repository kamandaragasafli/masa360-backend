"""Azərbaycan mətbəxi menyusu — salat, şorba, isti yemək, içki + şəkillər."""

from decimal import Decimal

from django.core.management.base import BaseCommand

from menu.models import Category, MenuItem
from restaurants.models import Restaurant


def img(photo_id: str) -> str:
    return (
        f'https://images.unsplash.com/{photo_id}'
        f'?w=800&h=600&fit=crop&crop=entropy'
    )


# (kateqoriya, ad, təsvir, qiymət AZN, şəkil URL)
MENU = [
    # —— Salatlar ——
    (
        'Salatlar',
        'Çoban salatı',
        'Qiymət aralığı: 5–9 ₼',
        '7.00',
        img('photo-1512621776951-a57141f2eefd'),
    ),
    (
        'Salatlar',
        'Manqal salatı',
        'Qiymət aralığı: 4–10 ₼',
        '7.00',
        img('photo-1544025162-d76694265947'),
    ),
    (
        'Salatlar',
        'Paytaxt salatı',
        'Qiymət aralığı: 5–7 ₼',
        '6.00',
        img('photo-1546069901-ba9599a7e63c'),
    ),
    (
        'Salatlar',
        'Sezar salatı (toyuqla)',
        'Qiymət aralığı: 11–15 ₼',
        '13.00',
        img('photo-1546793665-c74683f339c1'),
    ),
    (
        'Salatlar',
        'Sezar salatı (krevetlə)',
        'Qiymət aralığı: 12–16 ₼',
        '14.00',
        img('photo-1559339352-11d035aa65de'),
    ),
    (
        'Salatlar',
        'Mimoza salatı',
        'Qiymət aralığı: 6–8 ₼',
        '7.00',
        img('photo-1505253716362-afaea1d43f75'),
    ),
    (
        'Salatlar',
        'Gavurdağ salatı',
        'Qiymət aralığı: 6–8 ₼',
        '7.00',
        img('photo-1604909052743-94e838996d34'),
    ),
    (
        'Salatlar',
        'Pomidor-xiyar salatı',
        'Qiymət aralığı: 5–7 ₼',
        '6.00',
        img('photo-1607532941433-304659e8198a'),
    ),
    (
        'Salatlar',
        'Xırt-xırt badımcan salatı',
        'Qiymət aralığı: 5–7 ₼',
        '6.00',
        img('photo-1518977676601-b53f82aba655'),
    ),
    (
        'Salatlar',
        'Tərəvəz salatı (təzə)',
        'Qiymət aralığı: 4–6 ₼',
        '5.00',
        img('photo-1540420773420-3366772f4999'),
    ),
    # —— Şorbalar ——
    (
        'Şorbalar',
        'Düşbərə',
        'Qiymət aralığı: 3.5–8 ₼',
        '5.50',
        img('photo-1626804475297-41608ea09aeb'),
    ),
    (
        'Şorbalar',
        'Dovğa',
        'Qiymət aralığı: 2–6 ₼',
        '4.00',
        img('photo-1547592166-23ac45744acd'),
    ),
    (
        'Şorbalar',
        'Piti (Bakı/Şəki)',
        'Qiymət aralığı: 12–18 ₼',
        '15.00',
        img('photo-1604908176997-125f25cc6f3d'),
    ),
    (
        'Şorbalar',
        'Küftə-bozbaş',
        'Qiymət aralığı: 12–16 ₼',
        '14.00',
        img('photo-1529042410759-befb1204b468'),
    ),
    (
        'Şorbalar',
        'Mərci şorbası',
        'Qiymət aralığı: 4–6 ₼',
        '5.00',
        img('photo-1547591625-1b645efb9a4a'),
    ),
    (
        'Şorbalar',
        'Toyuq şorbası',
        'Qiymət aralığı: 4–6 ₼',
        '5.00',
        img('photo-1582878826629-29b7ad1cdc43'),
    ),
    (
        'Şorbalar',
        'Borş',
        'Qiymət aralığı: 5–7 ₼',
        '6.00',
        img('photo-1574484284002-952d92456975'),
    ),
    (
        'Şorbalar',
        'Xaş',
        'Qiymət aralığı: 6–10 ₼',
        '8.00',
        img('photo-1547592180-85f173990554'),
    ),
    # —— Milli isti yeməklər və kabablar ——
    (
        'Milli yeməklər',
        'Qutab (göyərti/ət/pendir/balqabaq)',
        '1 ədəd · qiymət aralığı: 1–4 ₼',
        '2.50',
        img('photo-1625944230946-1e3993906964'),
    ),
    (
        'Milli yeməklər',
        'Gürzə (qaynadılmış/qızardılmış)',
        'Qiymət aralığı: 10–15 ₼',
        '12.50',
        img('photo-1496116218417-1a781b1c416c'),
    ),
    (
        'Milli yeməklər',
        'Xəngəl',
        'Qiymət aralığı: 9–16 ₼',
        '12.50',
        img('photo-1585032226651-759b368d7246'),
    ),
    (
        'Milli yeməklər',
        'Yarpaq dolması',
        'Qiymət aralığı: 9–14 ₼',
        '11.50',
        img('photo-1599487488170-d11ec9c172f0'),
    ),
    (
        'Milli yeməklər',
        'Lülə kabab',
        'Qiymət aralığı: 10–15 ₼',
        '12.50',
        img('photo-1603360946369-dc9bb6258143'),
    ),
    (
        'Milli yeməklər',
        'Tikə kabab (quzu)',
        'Qiymət aralığı: 12–18 ₼',
        '15.00',
        img('photo-1555939594-58d7cb561ad1'),
    ),
    (
        'Milli yeməklər',
        'Toyuq kababı',
        'Qiymət aralığı: 8–12 ₼',
        '10.00',
        img('photo-1598103442097-8b74394b95c6'),
    ),
    (
        'Milli yeməklər',
        'Antrikot',
        'Qiymət aralığı: 14–18 ₼',
        '16.00',
        img('photo-1600891964092-4316c525677f'),
    ),
    (
        'Milli yeməklər',
        'Cız-bız',
        'Qiymət aralığı: 9–14 ₼',
        '11.50',
        img('photo-1432139555190-58524dae6a55'),
    ),
    (
        'Milli yeməklər',
        'Sac qovurma (quzu/toyuq)',
        'Qiymət aralığı: 19–28 ₼',
        '23.50',
        img('photo-1529042410759-befb1204b468'),
    ),
    (
        'Milli yeməklər',
        'Şah plov',
        '2 nəfərlik · qiymət aralığı: 20–30 ₼',
        '25.00',
        img('photo-1596797038530-2c107229654b'),
    ),
    (
        'Milli yeməklər',
        'Sabzi qovurma plov',
        'Qiymət aralığı: 15–25 ₼',
        '20.00',
        img('photo-1516684669134-de6f7c473a2a'),
    ),
    (
        'Milli yeməklər',
        'Quzu buğlama',
        'Qiymət aralığı: 20–28 ₼',
        '24.00',
        img('photo-1604908176997-125f25cc6f3d'),
    ),
    (
        'Milli yeməklər',
        'Nar qovurma (quzu/can əti)',
        'Qiymət aralığı: 13–24 ₼',
        '18.50',
        img('photo-1544025162-d76694265947'),
    ),
    (
        'Milli yeməklər',
        'Ləvəngi (toyuq/balıq)',
        'Qiymət aralığı: 15–25 ₼',
        '20.00',
        img('photo-1598103442097-8b74394b95c6'),
    ),
    (
        'Milli yeməklər',
        'Tabaka (toyuq)',
        'Qiymət aralığı: 18–25 ₼',
        '21.50',
        img('photo-1587593810167-a84920ea31be'),
    ),
    (
        'Milli yeməklər',
        'Dönər (toyuq/ət)',
        'Qiymət aralığı: 5–8 ₼',
        '6.50',
        img('photo-1626082927389-6cd097cdc6ec'),
    ),
    (
        'Milli yeməklər',
        'Lahmacun',
        'Qiymət aralığı: 4–7 ₼',
        '5.50',
        img('photo-1565299624946-b28f40a0ae38'),
    ),
    (
        'Milli yeməklər',
        'Kotlet (qazan/toyuq)',
        'Qiymət aralığı: 10–12 ₼',
        '11.00',
        img('photo-1529042410759-befb1204b468'),
    ),
    (
        'Milli yeməklər',
        'Pomidor-yumurta / Qayğanaq',
        'Qiymət aralığı: 5–7 ₼',
        '6.00',
        img('photo-1565299585323-38d6b0865b47'),
    ),
    # —— İçkilər ——
    (
        'İçkilər',
        'Ayran (kənd sayaqı)',
        'Qiymət aralığı: 2–4 ₼',
        '3.00',
        img('photo-1571212515416-fef01fc43637'),
    ),
    (
        'İçkilər',
        'Dovğa (içki kimi)',
        'Qiymət aralığı: 3–5 ₼',
        '4.00',
        img('photo-1623065422902-30a2d299bbe4'),
    ),
    (
        'İçkilər',
        'Kompot (reyhan/albalı)',
        'Qiymət aralığı: 2–4 ₼',
        '3.00',
        img('photo-1621506289937-a8e4df240d0b'),
    ),
    (
        'İçkilər',
        'Çay (çaynik)',
        'Qiymət aralığı: 2–5 ₼',
        '3.50',
        img('photo-1571934811356-5cc061b6821f'),
    ),
    (
        'İçkilər',
        'Qazlı su / mineral su',
        'Qiymət aralığı: 1.5–3 ₼',
        '2.00',
        img('photo-1548839140-29a749e1cf4d'),
    ),
    (
        'İçkilər',
        'Coca-Cola / Fanta / Sprite (0.33 l)',
        'Qiymət aralığı: 2–4 ₼',
        '3.00',
        img('photo-1554866585-cd94860890b7'),
    ),
    (
        'İçkilər',
        'Təzə şirə (nar/portağal)',
        'Qiymət aralığı: 4–7 ₼',
        '5.50',
        img('photo-1621506289937-a8e4df240d0b'),
    ),
    (
        'İçkilər',
        'Qatıq',
        'Qiymət aralığı: 2–3 ₼',
        '2.50',
        img('photo-1488477181946-6428a0291777'),
    ),
    (
        'İçkilər',
        'Kofe (americano/cappuccino)',
        'Qiymət aralığı: 3–6 ₼',
        '4.50',
        img('photo-1495474472287-4d71bcdd2085'),
    ),
    (
        'İçkilər',
        'Şərbət (nar/gül)',
        'Qiymət aralığı: 3–5 ₼',
        '4.00',
        img('photo-1544145945-f90425340c7e'),
    ),
]

CATEGORIES = [
    ('Salatlar', 0),
    ('Şorbalar', 1),
    ('Milli yeməklər', 2),
    ('İçkilər', 3),
]


class Command(BaseCommand):
    help = 'Azərbaycan mətbəxi menyusunu əlavə et (salat, şorba, kabab, içki + şəkil)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--slug',
            default='',
            help='Yalnız bu restoran (boş = bütün aktiv restoranlar)',
        )

    def handle(self, *args, **options):
        slug = (options.get('slug') or '').strip()
        if slug:
            restaurants = list(Restaurant.objects.filter(slug=slug))
            if not restaurants:
                self.stderr.write(f'Restoran tapılmadı: {slug}')
                return
        else:
            restaurants = list(Restaurant.objects.filter(is_active=True))

        for restaurant in restaurants:
            cats = {}
            for name, order in CATEGORIES:
                cat, _ = Category.objects.get_or_create(
                    restaurant=restaurant,
                    name=name,
                    defaults={'order': order, 'is_active': True},
                )
                if cat.order != order or not cat.is_active:
                    cat.order = order
                    cat.is_active = True
                    cat.save(update_fields=['order', 'is_active'])
                cats[name] = cat

            created_n = 0
            updated_n = 0
            for sort_i, (cat_name, name, desc, price, image_url) in enumerate(MENU):
                item, created = MenuItem.objects.get_or_create(
                    restaurant=restaurant,
                    name=name,
                    defaults={
                        'category': cats[cat_name],
                        'description': desc,
                        'price': Decimal(price),
                        'prep_time_minutes': 15,
                        'is_available': True,
                        'is_active': True,
                        'sort_order': sort_i,
                        'image_url': image_url,
                    },
                )
                if created:
                    created_n += 1
                else:
                    item.category = cats[cat_name]
                    item.description = desc
                    item.price = Decimal(price)
                    item.is_available = True
                    item.is_active = True
                    item.sort_order = sort_i
                    item.image_url = image_url
                    item.save()
                    updated_n += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f'{restaurant.slug}: +{created_n} new, {updated_n} updated '
                    f'({len(MENU)} items + images)'
                )
            )
