"""Müştəri QR / ağ label menyu — ictimai oxuma API."""

from django.db.models import Prefetch
from rest_framework.response import Response
from rest_framework.views import APIView

from menu.models import Category, MenuItem, Modifier, ModifierGroup
from restaurants.domains import (
    is_platform_host,
    normalize_domain,
    request_host,
    resolve_by_domain,
)
from restaurants.models import Restaurant
from restaurants.tenancy import resolve_restaurant
from tables.models import Table


def _item_image(item, request):
    if item.image:
        return item.image.url
    return item.image_url or ''


def _serialize_item(item, request):
    groups = []
    for g in item.modifier_groups.all():
        opts = [
            {
                'id': o.id,
                'name': o.name,
                'extra_price': str(o.extra_price),
            }
            for o in g.options.all()
            if o.is_available
        ]
        if not opts and g.is_required:
            continue
        groups.append(
            {
                'id': g.id,
                'name': g.name,
                'is_required': g.is_required,
                'min_select': g.min_select,
                'max_select': g.max_select,
                'options': opts,
            }
        )
    return {
        'id': item.id,
        'name': item.name,
        'description': item.description,
        'price': str(item.price),
        'image_url': _item_image(item, request),
        'prep_time_minutes': item.prep_time_minutes,
        'is_vegan': item.is_vegan,
        'is_gluten_free': item.is_gluten_free,
        'spicy_level': item.spicy_level,
        'modifier_groups': groups,
    }


def _restaurant_public(restaurant):
    logo = ''
    if restaurant.logo:
        logo = restaurant.logo.url
    return {
        'id': restaurant.id,
        'name': restaurant.name,
        'slug': restaurant.slug,
        'logo_url': logo,
        'currency': restaurant.currency or 'AZN',
        'qr_scan_mode': restaurant.qr_scan_mode,
        'address': restaurant.address,
        'phone': restaurant.phone,
        'delivery_enabled': restaurant.delivery_enabled,
        'storefront_enabled': restaurant.storefront_enabled,
        'custom_domain': restaurant.custom_domain or '',
        'shop_url': restaurant.public_shop_url(),
        'lat': restaurant.lat,
        'lng': restaurant.lng,
        'accept_cash': restaurant.accept_cash,
    }


class PublicResolveView(APIView):
    """
    GET /api/public/resolve/?host=thedöner.az
    Host header — ağ label domen → restoran.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        host = (
            request.query_params.get('host')
            or request.query_params.get('domain')
            or request_host(request)
        )
        host = normalize_domain(host)
        if not host or is_platform_host(host):
            return Response({'mode': 'platform', 'restaurant': None})
        restaurant = resolve_by_domain(host)
        if not restaurant:
            return Response(
                {
                    'mode': 'unknown',
                    'detail': 'Bu domenə bağlı restoran yoxdur',
                    'restaurant': None,
                },
                status=404,
            )
        if not restaurant.storefront_enabled:
            return Response(
                {
                    'mode': 'disabled',
                    'detail': 'Sifariş saytı müvəqqəti bağlıdır',
                    'restaurant': _restaurant_public(restaurant),
                },
                status=403,
            )
        return Response(
            {
                'mode': 'storefront',
                'restaurant': _restaurant_public(restaurant),
            }
        )


class PublicMenuView(APIView):
    """
    GET /api/public/menu/?slug=…&table=5
    GET /api/public/menu/?domain=thedöner.az
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        slug = request.query_params.get('slug', '').strip()
        table_number = request.query_params.get('table', '')

        restaurant = resolve_restaurant(request)
        if not restaurant and slug:
            restaurant = Restaurant.objects.filter(
                slug=slug, is_active=True
            ).first()
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        online_mode = not table_number
        if online_mode:
            open_ok = (
                restaurant.storefront_enabled
                or restaurant.delivery_enabled
                or restaurant.qr_enabled
            )
            if not open_ok:
                return Response(
                    {'detail': 'Onlayn menyu bu restoran üçün bağlıdır'},
                    status=403,
                )
        elif not restaurant.qr_enabled:
            return Response(
                {'detail': 'QR menyu bu restoran üçün deaktivdir'},
                status=403,
            )

        table = (
            Table.objects.filter(
                restaurant=restaurant, number=str(table_number)
            ).first()
            if table_number
            else None
        )
        if table_number and not table:
            return Response({'detail': 'Masa tapılmadı'}, status=404)
        if table and not table.qr_enabled:
            return Response(
                {'detail': 'Bu masanın QR menyusu bağlıdır'},
                status=403,
            )

        item_qs = (
            MenuItem.objects.filter(is_active=True, is_available=True)
            .prefetch_related(
                Prefetch(
                    'modifier_groups',
                    queryset=ModifierGroup.objects.prefetch_related(
                        Prefetch(
                            'options',
                            queryset=Modifier.objects.filter(
                                is_available=True
                            ).order_by('order', 'id'),
                        )
                    ).order_by('order', 'id'),
                )
            )
            .order_by('sort_order', 'name')
        )

        categories = (
            Category.objects.filter(restaurant=restaurant, is_active=True)
            .prefetch_related(Prefetch('items', queryset=item_qs))
            .order_by('order', 'name')
        )

        cats = []
        for c in categories:
            items = [_serialize_item(i, request) for i in c.items.all()]
            if items:
                cats.append({'id': c.id, 'name': c.name, 'items': items})

        return Response(
            {
                'restaurant': _restaurant_public(restaurant),
                'mode': 'delivery' if not table else 'dine_in',
                'table': (
                    {
                        'id': table.id,
                        'number': table.number,
                    }
                    if table
                    else None
                ),
                'categories': cats,
            }
        )
