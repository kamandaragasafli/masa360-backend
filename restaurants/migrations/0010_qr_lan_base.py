# Generated manually

from django.conf import settings
from django.db import migrations, models


def force_lan_qr_base(apps, schema_editor):
    Restaurant = apps.get_model('restaurants', 'Restaurant')
    lan = getattr(settings, 'PUBLIC_MENU_BASE', 'http://127.0.0.1:5173')
    for r in Restaurant.objects.all():
        base = (r.qr_menu_base_url or '').strip()
        host = (
            base.replace('https://', '')
            .replace('http://', '')
            .split('/')[0]
            .split(':')[0]
            .lower()
        )
        is_local = (
            host in ('localhost', '127.0.0.1', '0.0.0.0')
            or host.startswith('192.168.')
            or host.startswith('10.')
            or host.startswith('172.')
        )
        if not base or not is_local:
            r.qr_menu_base_url = lan
            r.save(update_fields=['qr_menu_base_url'])


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0009_subscription_interval_expiry'),
    ]

    operations = [
        migrations.AlterField(
            model_name='restaurant',
            name='qr_menu_base_url',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Müştəri menyusu bazası (LAN: http://192.168.x.x:5173)',
                max_length=255,
            ),
        ),
        migrations.RunPython(force_lan_qr_base, migrations.RunPython.noop),
    ]
