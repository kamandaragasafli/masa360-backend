from decimal import Decimal, InvalidOperation
from datetime import datetime

from django.db.models import Prefetch
from rest_framework.response import Response
from rest_framework.views import APIView

from restaurants.tenancy import resolve_restaurant

from .models import (
    IngredientBatch,
    IngredientCategory,
    RawIngredient,
    WasteLog,
)
from .services import (
    receive_batch,
    record_waste,
    serialize_ingredient,
    stock_alerts,
)


def _restaurant(request):
    return resolve_restaurant(request)


def _warn_days(restaurant) -> int:
    return int(getattr(restaurant, 'notify_expiry_days', 7) or 7)


class WarehouseAlertsView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        return Response(stock_alerts(restaurant))


class IngredientCategoryListView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        cats = IngredientCategory.objects.filter(
            restaurant=restaurant, is_active=True
        )
        data = []
        for c in cats:
            count = c.ingredients.filter(is_active=True).count()
            data.append(
                {
                    'id': c.id,
                    'name': c.name,
                    'order': c.order,
                    'items_count': count,
                }
            )
        return Response(data)

    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'detail': 'Ad tələb olunur'}, status=400)
        cat = IngredientCategory.objects.create(
            restaurant=restaurant,
            name=name[:100],
            order=IngredientCategory.objects.filter(
                restaurant=restaurant
            ).count(),
        )
        return Response(
            {'id': cat.id, 'name': cat.name, 'order': cat.order, 'items_count': 0},
            status=201,
        )


class IngredientListView(APIView):
    """
    GET ?slug=&category=&filter=all|urgent|low|expiring&search=
    """

    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        warn_days = _warn_days(restaurant)
        filt = (request.query_params.get('filter') or 'all').strip()
        category = request.query_params.get('category')
        search = (request.query_params.get('search') or '').strip()

        qs = (
            RawIngredient.objects.filter(
                restaurant=restaurant, is_active=True
            )
            .select_related('category')
            .prefetch_related(
                Prefetch(
                    'batches',
                    queryset=IngredientBatch.objects.filter(
                        remaining_quantity__gt=0
                    ).order_by('expiry_date', 'received_at'),
                )
            )
            .order_by('name')
        )
        if category:
            qs = qs.filter(category_id=category)
        if search:
            qs = qs.filter(name__icontains=search)

        rows = []
        for ing in qs:
            batches = list(ing.batches.all())
            row = serialize_ingredient(
                ing, warn_days=warn_days, batches=batches
            )
            if filt == 'urgent' and row['tone'] != 'urgent':
                continue
            if filt == 'low' and not row['is_low_stock']:
                continue
            if filt == 'expiring':
                if not any(
                    b['tone'] in ('urgent', 'warn', 'expired')
                    for b in row['batches']
                ):
                    continue
            rows.append(row)
        return Response(rows)

    def post(self, request):
        """Yeni xammal yarat."""
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'detail': 'Ad tələb olunur'}, status=400)
        unit = request.data.get('unit') or 'kg'
        if unit not in dict(RawIngredient.UNIT_CHOICES):
            unit = 'kg'
        cat_id = request.data.get('category_id')
        category = None
        if cat_id:
            category = IngredientCategory.objects.filter(
                pk=cat_id, restaurant=restaurant
            ).first()
        try:
            min_stock = Decimal(str(request.data.get('min_stock') or '1'))
        except (InvalidOperation, TypeError):
            min_stock = Decimal('1')
        ing, created = RawIngredient.objects.get_or_create(
            restaurant=restaurant,
            name=name[:120],
            defaults={
                'unit': unit,
                'category': category,
                'min_stock': min_stock,
            },
        )
        if not created and category and not ing.category_id:
            ing.category = category
            ing.save(update_fields=['category'])
        return Response(
            serialize_ingredient(ing, warn_days=_warn_days(restaurant)),
            status=201 if created else 200,
        )


class BatchReceiveView(APIView):
    """POST — mal qəbulu → yeni IngredientBatch."""

    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)

        ingredient_id = request.data.get('ingredient_id')
        name = (request.data.get('name') or '').strip()
        unit = request.data.get('unit') or 'kg'
        category_id = request.data.get('category_id')

        ingredient = None
        if ingredient_id:
            ingredient = RawIngredient.objects.filter(
                pk=ingredient_id, restaurant=restaurant
            ).first()
        elif name:
            category = None
            if category_id:
                category = IngredientCategory.objects.filter(
                    pk=category_id, restaurant=restaurant
                ).first()
            if unit not in dict(RawIngredient.UNIT_CHOICES):
                unit = 'kg'
            try:
                min_stock = Decimal(
                    str(request.data.get('min_stock') or '1')
                )
            except (InvalidOperation, TypeError):
                min_stock = Decimal('1')
            ingredient, _ = RawIngredient.objects.get_or_create(
                restaurant=restaurant,
                name=name[:120],
                defaults={
                    'unit': unit,
                    'category': category,
                    'min_stock': min_stock,
                },
            )
        if not ingredient:
            return Response(
                {'detail': 'Xammal seçin və ya ad yazın'}, status=400
            )

        try:
            quantity = Decimal(str(request.data.get('quantity')))
        except (InvalidOperation, TypeError):
            return Response({'detail': 'Miqdar yanlışdır'}, status=400)

        expiry_raw = request.data.get('expiry_date') or ''
        expiry_date = None
        if expiry_raw:
            try:
                expiry_date = datetime.strptime(
                    str(expiry_raw)[:10], '%Y-%m-%d'
                ).date()
            except ValueError:
                return Response(
                    {'detail': 'Son istifadə tarixi yanlışdır'}, status=400
                )

        supplier = (request.data.get('supplier') or '').strip()
        note = (request.data.get('note') or '').strip()
        invoice = request.FILES.get('invoice_image')

        user = getattr(request, 'user', None)
        try:
            batch = receive_batch(
                ingredient=ingredient,
                quantity=quantity,
                expiry_date=expiry_date,
                supplier=supplier,
                note=note,
                invoice_image=invoice,
                user=user if user and user.is_authenticated else None,
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

        ingredient.refresh_from_db()
        return Response(
            {
                'batch_id': batch.id,
                'ingredient': serialize_ingredient(
                    ingredient, warn_days=_warn_days(restaurant)
                ),
            },
            status=201,
        )


class WasteCreateView(APIView):
    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        batch_id = request.data.get('batch_id')
        batch = (
            IngredientBatch.objects.select_related('ingredient')
            .filter(pk=batch_id, ingredient__restaurant=restaurant)
            .first()
        )
        if not batch:
            return Response({'detail': 'Partiya tapılmadı'}, status=404)
        try:
            quantity = Decimal(str(request.data.get('quantity')))
        except (InvalidOperation, TypeError):
            return Response({'detail': 'Miqdar yanlışdır'}, status=400)
        reason = request.data.get('reason') or 'other'
        if reason not in dict(WasteLog.REASON_CHOICES):
            reason = 'other'
        note = (request.data.get('note') or '').strip()
        user = getattr(request, 'user', None)
        try:
            log = record_waste(
                batch=batch,
                quantity=quantity,
                reason=reason,
                note=note,
                user=user if user and user.is_authenticated else None,
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        batch.ingredient.refresh_from_db()
        return Response(
            {
                'waste_id': log.id,
                'ingredient': serialize_ingredient(
                    batch.ingredient, warn_days=_warn_days(restaurant)
                ),
            },
            status=201,
        )
