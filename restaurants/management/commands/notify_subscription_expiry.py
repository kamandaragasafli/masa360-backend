"""
Abunəlik bitməsinə 3 gün və daha az qalan restoranlara gündəlik bildiriş.

Cron nümunəsi (hər gün səhər):
  python manage.py notify_subscription_expiry
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.models import Notification
from notifications.services import create_notification
from restaurants.models import Restaurant


class Command(BaseCommand):
    help = 'Abunəlik bitməsinə ≤3 gün qalanlara gündəlik bildiriş göndər'

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate()
        window_end = now + timedelta(days=3)

        qs = Restaurant.objects.filter(
            is_active=True,
        ).exclude(subscription_plan='').exclude(
            subscription_expires_at=None
        ).filter(
            subscription_expires_at__gt=now,
            subscription_expires_at__lte=window_end,
        )

        sent = 0
        skipped = 0
        for restaurant in qs:
            already = Notification.objects.filter(
                restaurant=restaurant,
                type='subscription_expiry',
                created_at__date=today,
            ).exists()
            if already:
                skipped += 1
                continue

            expires = restaurant.subscription_expires_at
            days_left = max(0, (expires.date() - today).days)
            if days_left == 0:
                when = 'bu gün'
            elif days_left == 1:
                when = '1 gün'
            else:
                when = f'{days_left} gün'

            create_notification(
                restaurant=restaurant,
                type='subscription_expiry',
                recipient_role='manager',
                priority='critical',
                title='Abunəlik bitmək üzrədir',
                message=(
                    f'Abunəliyiniz {when} sonra bitir '
                    f'({expires.astimezone().strftime("%d.%m.%Y")}). '
                    f'Ayarlar → Hesab-dan yeniləyin.'
                ),
                link='/settings',
            )
            sent += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f'{restaurant.slug}: {days_left}d left — notified'
                )
            )

        self.stdout.write(
            self.style.NOTICE(f'sent={sent} skipped={skipped}')
        )
