# Generated manually

from django.db import migrations, models


def seed_existing_plans(apps, schema_editor):
    Restaurant = apps.get_model('restaurants', 'Restaurant')
    Restaurant.objects.filter(subscription_plan='').update(subscription_plan='pro')


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0007_online_delivery_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='restaurant',
            name='subscription_plan',
            field=models.CharField(
                blank=True,
                choices=[
                    ('start', 'Başlanğıc'),
                    ('pro', 'Pro'),
                    ('net', 'Şəbəkə'),
                ],
                default='',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='restaurant',
            name='subscription_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(seed_existing_plans, migrations.RunPython.noop),
    ]
