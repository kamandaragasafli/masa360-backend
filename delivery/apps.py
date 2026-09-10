from django.apps import AppConfig


class DeliveryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'delivery'
    verbose_name = 'Çatdırılma / Kuryer'

    def ready(self):
        from . import signals  # noqa: F401
