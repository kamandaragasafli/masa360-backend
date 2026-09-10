from django.db.models import Count, Q
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.tenancy import resolve_restaurant

from .models import Category, MenuItem
from .serializers import (
    CategorySerializer,
    MenuItemDetailSerializer,
    MenuItemListSerializer,
    normalize_menu_item_data,
)


def _restaurant(request):
    return resolve_restaurant(request)

class CategoryListCreateView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        qs = (
            Category.objects.filter(restaurant=restaurant)
            .annotate(
                items_count=Count('items'),
                active_items_count=Count('items', filter=Q(items__is_active=True)),
                unavailable_count=Count(
                    'items', filter=Q(items__is_available=False)
                ),
            )
            .order_by('order', 'name')
        )
        return Response(CategorySerializer(qs, many=True).data)

    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        max_order = (
            Category.objects.filter(restaurant=restaurant)
            .order_by('-order')
            .values_list('order', flat=True)
            .first()
            or 0
        )
        category = serializer.save(restaurant=restaurant, order=max_order + 1)
        category.items_count = 0
        category.active_items_count = 0
        return Response(CategorySerializer(category).data, status=201)


class CategoryDetailView(APIView):
    def patch(self, request, pk):
        category = Category.objects.filter(pk=pk).first()
        if not category:
            return Response({'detail': 'Kateqoriya tapılmadı'}, status=404)
        serializer = CategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        category = (
            Category.objects.filter(pk=pk)
            .annotate(
                items_count=Count('items'),
                active_items_count=Count('items', filter=Q(items__is_active=True)),
                unavailable_count=Count(
                    'items', filter=Q(items__is_available=False)
                ),
            )
            .first()
        )
        return Response(CategorySerializer(category).data)

    def delete(self, request, pk):
        category = Category.objects.filter(pk=pk).first()
        if not category:
            return Response({'detail': 'Kateqoriya tapılmadı'}, status=404)
        category.delete()
        return Response(status=204)


class CategoryReorderView(APIView):
    def post(self, request):
        """Body: { "order": [id1, id2, ...] }"""
        ids = request.data.get('order', [])
        for index, cat_id in enumerate(ids):
            Category.objects.filter(pk=cat_id).update(order=index)
        return Response({'ok': True})


class MenuItemListCreateView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        qs = MenuItem.objects.filter(restaurant=restaurant).select_related('category')
        category_id = request.query_params.get('category')
        search = request.query_params.get('search', '').strip()
        if category_id:
            qs = qs.filter(category_id=category_id)
        if search:
            qs = qs.filter(name__icontains=search)
        qs = qs.annotate(
            modifiers_count=Count('modifier_groups')
        ).order_by('sort_order', 'name')
        return Response(
            MenuItemListSerializer(qs, many=True, context={'request': request}).data
        )

    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        data = normalize_menu_item_data(request.data)
        serializer = MenuItemDetailSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save(restaurant=restaurant)
        item = (
            MenuItem.objects.filter(pk=item.pk)
            .prefetch_related('modifier_groups__options')
            .select_related('category')
            .first()
        )
        return Response(
            MenuItemDetailSerializer(item, context={'request': request}).data,
            status=201,
        )


class MenuItemDetailView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, pk):
        item = (
            MenuItem.objects.filter(pk=pk)
            .prefetch_related('modifier_groups__options')
            .select_related('category')
            .first()
        )
        if not item:
            return Response({'detail': 'Məhsul tapılmadı'}, status=404)
        return Response(
            MenuItemDetailSerializer(item, context={'request': request}).data
        )

    def patch(self, request, pk):
        item = (
            MenuItem.objects.filter(pk=pk)
            .prefetch_related('modifier_groups__options')
            .first()
        )
        if not item:
            return Response({'detail': 'Məhsul tapılmadı'}, status=404)

        data = normalize_menu_item_data(request.data)
        serializer = MenuItemDetailSerializer(
            item,
            data=data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        item = (
            MenuItem.objects.filter(pk=item.pk)
            .prefetch_related('modifier_groups__options')
            .select_related('category')
            .first()
        )
        return Response(
            MenuItemDetailSerializer(item, context={'request': request}).data
        )

    def delete(self, request, pk):
        item = MenuItem.objects.filter(pk=pk).first()
        if not item:
            return Response({'detail': 'Məhsul tapılmadı'}, status=404)
        item.delete()
        return Response(status=204)


class MenuItemToggleView(APIView):
    def post(self, request, pk):
        item = MenuItem.objects.filter(pk=pk).first()
        if not item:
            return Response({'detail': 'Məhsul tapılmadı'}, status=404)
        field = request.data.get('field', 'is_available')
        if field not in ('is_available', 'is_active'):
            return Response({'detail': 'Yanlış field'}, status=400)
        setattr(item, field, not getattr(item, field))
        item.save(update_fields=[field])
        return Response(
            MenuItemListSerializer(item, context={'request': request}).data
        )


class MenuBulkUpdateView(APIView):
    def post(self, request):
        ids = request.data.get('ids', [])
        if not ids:
            return Response({'detail': 'ids boşdur'}, status=400)
        qs = MenuItem.objects.filter(pk__in=ids)
        updated = {}
        if 'price_percent' in request.data:
            percent = float(request.data['price_percent'])
            for item in qs:
                item.price = round(float(item.price) * (1 + percent / 100), 2)
                item.save(update_fields=['price'])
            updated['price_percent'] = percent
        if 'category' in request.data:
            qs.update(category_id=request.data['category'])
            updated['category'] = request.data['category']
        if 'is_available' in request.data:
            qs.update(is_available=bool(request.data['is_available']))
            updated['is_available'] = request.data['is_available']
        if 'is_active' in request.data:
            qs.update(is_active=bool(request.data['is_active']))
            updated['is_active'] = request.data['is_active']
        return Response({'ok': True, 'updated': updated, 'count': qs.count()})
