import json

from rest_framework import serializers

from .models import Category, MenuItem, Modifier, ModifierGroup


BOOL_KEYS = (
    'is_available',
    'is_active',
    'is_vegan',
    'is_gluten_free',
)


def normalize_menu_item_data(data):
    """JSON ve multipart FormData-ni serializer ucun vahid dict-e cevirir."""
    if hasattr(data, 'keys'):
        raw = {}
        for key in data.keys():
            if key == 'image':
                file_val = data.get(key)
                if file_val not in (None, '', 'null'):
                    raw['image'] = file_val
                continue
            raw[key] = data.get(key)
    else:
        raw = dict(data)

    out = {}
    for key, val in raw.items():
        if key == 'modifier_groups':
            if isinstance(val, str):
                out[key] = json.loads(val) if val.strip() else []
            else:
                out[key] = val or []
        elif key in BOOL_KEYS:
            if isinstance(val, bool):
                out[key] = val
            else:
                out[key] = str(val).lower() in ('1', 'true', 'yes', 'on')
        elif key == 'external_image_url':
            out[key] = val or ''
        elif key == 'image_url' and isinstance(val, str):
            out['external_image_url'] = val
        else:
            out[key] = val
    return out


class ModifierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Modifier
        fields = (
            'id',
            'name',
            'extra_price',
            'is_available',
            'order',
        )


class ModifierGroupSerializer(serializers.ModelSerializer):
    options = ModifierSerializer(many=True, required=False)

    class Meta:
        model = ModifierGroup
        fields = (
            'id',
            'name',
            'is_required',
            'min_select',
            'max_select',
            'order',
            'options',
        )


class MenuItemListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True, default=None
    )
    spicy_label = serializers.CharField(
        source='get_spicy_level_display', read_only=True
    )
    image_url = serializers.SerializerMethodField()
    has_modifiers = serializers.SerializerMethodField()
    modifiers_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = MenuItem
        fields = (
            'id',
            'name',
            'description',
            'price',
            'category',
            'category_name',
            'image',
            'image_url',
            'is_available',
            'is_active',
            'prep_time_minutes',
            'is_vegan',
            'is_gluten_free',
            'spicy_level',
            'spicy_label',
            'sort_order',
            'has_modifiers',
            'modifiers_count',
        )

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return obj.image_url or None

    def get_has_modifiers(self, obj):
        if hasattr(obj, 'modifiers_count'):
            return (obj.modifiers_count or 0) > 0
        return obj.modifier_groups.exists()


class MenuItemDetailSerializer(MenuItemListSerializer):
    modifier_groups = ModifierGroupSerializer(many=True, required=False)
    external_image_url = serializers.CharField(
        required=False, allow_blank=True, write_only=True
    )

    class Meta(MenuItemListSerializer.Meta):
        fields = MenuItemListSerializer.Meta.fields + (
            'modifier_groups',
            'external_image_url',
        )

    def create(self, validated_data):
        groups_data = validated_data.pop('modifier_groups', [])
        external_url = validated_data.pop('external_image_url', None)
        item = MenuItem.objects.create(**validated_data)
        if external_url and not validated_data.get('image') and not item.image:
            item.image_url = external_url
            item.save(update_fields=['image_url'])
        self._save_groups(item, groups_data)
        return item

    def update(self, instance, validated_data):
        groups_data = validated_data.pop('modifier_groups', None)
        external_url = validated_data.pop('external_image_url', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if external_url is not None:
            instance.image_url = external_url
        instance.save()
        if groups_data is not None:
            instance.modifier_groups.all().delete()
            self._save_groups(instance, groups_data)
        return instance

    def _save_groups(self, item, groups_data):
        for g_index, group_data in enumerate(groups_data):
            options = list(group_data.get('options') or [])
            group = ModifierGroup.objects.create(
                menu_item=item,
                order=group_data.get('order', g_index),
                name=group_data.get('name', ''),
                is_required=group_data.get('is_required', False),
                min_select=group_data.get('min_select', 0),
                max_select=group_data.get('max_select', 1),
            )
            for o_index, opt in enumerate(options):
                Modifier.objects.create(
                    group=group,
                    order=opt.get('order', o_index),
                    name=opt.get('name', ''),
                    extra_price=opt.get('extra_price', 0),
                    is_available=opt.get('is_available', True),
                )


class CategorySerializer(serializers.ModelSerializer):
    items_count = serializers.IntegerField(read_only=True, required=False)
    active_items_count = serializers.IntegerField(read_only=True, required=False)
    unavailable_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Category
        fields = (
            'id',
            'name',
            'order',
            'is_active',
            'printer',
            'items_count',
            'active_items_count',
            'unavailable_count',
            'restaurant',
        )
        read_only_fields = ('restaurant',)
