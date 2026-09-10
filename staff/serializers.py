from rest_framework import serializers

from .models import StaffUser


class StaffSerializer(serializers.ModelSerializer):
    role_label = serializers.CharField(source='get_role_display', read_only=True)
    has_pin = serializers.BooleanField(read_only=True)
    initials = serializers.CharField(read_only=True)
    # Yazı üçün — oxumada heç vaxt qayıtmır
    pin_code = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = StaffUser
        fields = (
            'id',
            'full_name',
            'role',
            'role_label',
            'pin_code',
            'has_pin',
            'initials',
            'is_active',
            'can_discount',
            'can_edit_menu',
            'can_cancel_preparing_order',
        )

    def validate_pin_code(self, value):
        if value in (None, ''):
            return value
        if not str(value).isdigit() or not (4 <= len(str(value)) <= 6):
            raise serializers.ValidationError('PIN 4–6 rəqəm olmalıdır')
        return str(value)

    def create(self, validated_data):
        raw_pin = validated_data.pop('pin_code', None)
        staff = StaffUser(**validated_data)
        if raw_pin:
            staff.set_pin(raw_pin)
        staff.save()
        return staff

    def update(self, instance, validated_data):
        raw_pin = validated_data.pop('pin_code', None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        if raw_pin:
            instance.set_pin(raw_pin)
        instance.save()
        return instance
