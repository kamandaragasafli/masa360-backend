# Generated manually

from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def backfill_expiry(apps, schema_editor):
    Restaurant = apps.get_model('restaurants', 'Restaurant')
    now = timezone.now()
    for r in Restaurant.objects.exclude(subscription_plan=''):
        updates = {}
        if not r.subscription_interval:
            updates['subscription_interval'] = 'monthly'
        if not r.subscription_expires_at:
            start = r.subscription_at or now
            updates['subscription_expires_at'] = start + timedelta(days=30)
        if updates:
            for k, v in updates.items():
                setattr(r, k, v)
            r.save(update_fields=list(updates.keys()))


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0008_restaurant_subscription'),
    ]

    operations = [
        migrations.AddField(
            model_name='restaurant',
            name='subscription_interval',
            field=models.CharField(
                blank=True,
                choices=[('monthly', 'Aylıq'), ('yearly', 'Illik')],
                default='',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='restaurant',
            name='subscription_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='restaurant',
            name='subscription_amount',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=10, null=True
            ),
        ),
        migrations.RunPython(backfill_expiry, migrations.RunPython.noop),
    ]
