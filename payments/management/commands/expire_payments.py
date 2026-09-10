from django.core.management.base import BaseCommand
from django.utils import timezone

from payments.models import Payment


class Command(BaseCommand):
    help = 'Vaxtı keçmiş pending/processing ödənişləri expired edir (15 dəq default)'

    def handle(self, *args, **options):
        now = timezone.now()
        n = Payment.objects.filter(
            status__in=('pending', 'processing'),
            expires_at__lt=now,
        ).update(status='expired')
        self.stdout.write(self.style.SUCCESS(f'Expired: {n}'))
