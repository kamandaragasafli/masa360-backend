# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='type',
            field=models.CharField(
                choices=[
                    ('order_ready', 'Sifariş hazırdır'),
                    ('waiter_call', 'Ofisiant çağırışı'),
                    ('bill_request', 'Hesab istəyi'),
                    ('new_order', 'Yeni sifariş'),
                    ('new_qr_order', 'Yeni QR sifarişi'),
                    ('order_cancelled', 'Sifariş ləğv edildi'),
                    ('low_stock', 'Stok azalıb'),
                    ('expiry_warning', 'Son istifadə tarixi'),
                    ('payment_failed', 'Ödəniş uğursuz'),
                    ('daily_summary', 'Gündəlik xülasə'),
                    ('cancel_spike', 'Qeyri-adi ləğv sayı'),
                    ('subscription_expiry', 'Abunəlik bitir'),
                ],
                max_length=30,
            ),
        ),
    ]
