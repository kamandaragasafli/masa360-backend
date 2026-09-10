from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from delivery.models import Courier
from restaurants.models import Restaurant
from staff.models import StaffUser


class Command(BaseCommand):
    help = 'Demo kuryer: Elçin / PIN 4444'

    def handle(self, *args, **options):
        restaurant = Restaurant.objects.filter(slug='surfues-resto').first()
        if not restaurant:
            self.stderr.write('surfues-resto tapılmadı')
            return

        restaurant.delivery_enabled = True
        if not restaurant.delivery_fee_amount:
            restaurant.delivery_fee_amount = 18
        if not restaurant.address:
            restaurant.address = 'Nizami küç. 1'
        restaurant.save()

        staff = StaffUser.objects.filter(
            restaurant=restaurant, role='courier', full_name='Elçin'
        ).first()
        if not staff:
            user, _ = User.objects.get_or_create(
                username='courier_elcin',
                defaults={'first_name': 'Elçin'},
            )
            staff = StaffUser(
                restaurant=restaurant,
                user=user,
                full_name='Elçin',
                role='courier',
                is_active=True,
            )
            staff.set_pin('4444')
            staff.save()
        else:
            staff.set_pin('4444')
            staff.is_active = True
            staff.save()

        courier, created = Courier.objects.get_or_create(
            staff=staff,
            defaults={
                'user': staff.user,
                'restaurant': restaurant,
                'full_name': 'Elçin',
                'phone': '+994551112233',
                'is_available': False,
            },
        )
        if not created:
            courier.restaurant = restaurant
            courier.full_name = 'Elçin'
            courier.phone = courier.phone or '+994551112233'
            courier.user = staff.user
            courier.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'Courier ready: Elcin (staff_id={staff.id}, '
                f'courier_id={courier.id}, PIN=4444)'
            )
        )
