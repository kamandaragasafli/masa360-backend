from django.db.models.signals import post_save
from django.dispatch import receiver

from staff.models import StaffUser


@receiver(post_save, sender=StaffUser)
def sync_courier_profile(sender, instance: StaffUser, **kwargs):
    """Ayarlar → İşçilər: role=courier olanda Courier profili yaradılır."""
    if instance.role != 'courier' or not instance.is_active:
        return
    try:
        from delivery.services import ensure_courier_profile

        ensure_courier_profile(instance)
    except Exception:
        pass
