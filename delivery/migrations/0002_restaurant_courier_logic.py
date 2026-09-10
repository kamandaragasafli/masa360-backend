from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def fix_courier_rows(apps, schema_editor):
    Courier = apps.get_model('delivery', 'Courier')
    Restaurant = apps.get_model('restaurants', 'Restaurant')
    StaffUser = apps.get_model('staff', 'StaffUser')
    default_resto = Restaurant.objects.first()
    for c in Courier.objects.all():
        if c.staff_id:
            staff = StaffUser.objects.filter(pk=c.staff_id).first()
            if staff:
                c.restaurant_id = staff.restaurant_id
                c.save(update_fields=['restaurant_id'])
                continue
        if not c.restaurant_id and default_resto:
            c.restaurant_id = default_resto.id
            c.save(update_fields=['restaurant_id'])
    DeliveryAssignment = apps.get_model('delivery', 'DeliveryAssignment')
    DeliveryAssignment.objects.filter(status='expired').update(status='failed')


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0001_initial'),
        ('orders', '0003_order_cancelled_at_order_cancelled_note_and_more'),
        ('restaurants', '0006_restaurant_device_setup_code'),
        ('staff', '0004_staffuser_can_cancel_preparing_order_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(fix_courier_rows, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='courier',
            name='restaurant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='couriers',
                to='restaurants.restaurant',
            ),
        ),
        migrations.AlterField(
            model_name='courier',
            name='staff',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='courier_profile',
                to='staff.staffuser',
            ),
        ),
        migrations.AlterField(
            model_name='courier',
            name='user',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='courier_profile',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='deliveryassignment',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='deliveryassignment',
            name='offered_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='deliveryassignment',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Kuryer axtarılır'),
                    ('offered', 'Təklif edildi'),
                    ('accepted', 'Qəbul edildi'),
                    ('picked_up', 'Götürüldü'),
                    ('delivered', 'Çatdırıldı'),
                    ('failed', 'Uğursuz — kuryer tapılmadı'),
                    ('cancelled', 'Ləğv'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AlterModelOptions(
            name='deliveryassignment',
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Çatdırılma tapşırığı',
                'verbose_name_plural': 'Çatdırılma tapşırıqları',
            },
        ),
    ]
