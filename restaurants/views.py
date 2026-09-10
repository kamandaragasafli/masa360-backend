from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from menu.models import Category
from menu.serializers import CategorySerializer

from .models import KitchenPrinter, Restaurant
from .serializers import (
    KitchenPrinterSerializer,
    RestaurantSerializer,
)


from .tenancy import resolve_restaurant


def _restaurant(request):
    return resolve_restaurant(request)



class CurrentRestaurantView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        return Response(
            RestaurantSerializer(restaurant, context={'request': request}).data
        )

    def patch(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        data = request.data.copy()
        if hasattr(data, 'dict'):
            data = data.dict()
            # MultiValueDict — faylları ayrıca
            if request.FILES.get('logo'):
                data['logo'] = request.FILES['logo']
        # FormData boolean / JSON stringlər
        for key in list(data.keys()):
            val = data.get(key)
            if isinstance(val, str) and val.lower() in ('true', 'false'):
                data[key] = val.lower() == 'true'
        if isinstance(data.get('opening_hours'), str):
            import json

            try:
                data['opening_hours'] = json.loads(data['opening_hours'])
            except json.JSONDecodeError:
                data.pop('opening_hours', None)
        ser = RestaurantSerializer(
            restaurant,
            data=data,
            partial=True,
            context={'request': request},
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        restaurant.refresh_from_db()
        return Response(
            RestaurantSerializer(restaurant, context={'request': request}).data
        )


class KitchenPrinterListCreateView(APIView):
    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        qs = restaurant.printers.all()
        return Response(KitchenPrinterSerializer(qs, many=True).data)

    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        ser = KitchenPrinterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        printer = ser.save(restaurant=restaurant)
        return Response(KitchenPrinterSerializer(printer).data, status=201)


class KitchenPrinterDetailView(APIView):
    def patch(self, request, pk):
        restaurant = _restaurant(request)
        printer = KitchenPrinter.objects.filter(pk=pk).first()
        if not printer or (
            restaurant and printer.restaurant_id != restaurant.id
        ):
            return Response({'detail': 'Printer tapılmadı'}, status=404)
        ser = KitchenPrinterSerializer(
            printer, data=request.data, partial=True
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(KitchenPrinterSerializer(printer).data)

    def delete(self, request, pk):
        restaurant = _restaurant(request)
        printer = KitchenPrinter.objects.filter(pk=pk).first()
        if not printer or (
            restaurant and printer.restaurant_id != restaurant.id
        ):
            return Response({'detail': 'Printer tapılmadı'}, status=404)
        printer.delete()
        return Response(status=204)


class KitchenPrinterTestView(APIView):
    def post(self, request, pk):
        import time

        from orders.kot import enqueue_test_print
        from orders.models import PrintJob

        restaurant = _restaurant(request)
        printer = KitchenPrinter.objects.filter(pk=pk).first()
        if not printer or (
            restaurant and printer.restaurant_id != restaurant.id
        ):
            return Response({'detail': 'Printer tapılmadı'}, status=404)

        job = enqueue_test_print(printer)
        time.sleep(0.25)
        job = PrintJob.objects.filter(pk=job.pk).first()
        return Response(
            {
                'id': job.id,
                'status': job.status,
                'error_message': job.error_message,
                'printer': job.printer_id,
                'is_test': job.is_test,
            }
        )

class CategoryPrinterMapView(APIView):
    """Kateqoriya → printer bağlama (toplu)."""

    def get(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        qs = Category.objects.filter(restaurant=restaurant).order_by(
            'order', 'name'
        )
        return Response(CategorySerializer(qs, many=True).data)

    def post(self, request):
        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        mapping = request.data.get('mapping') or []
        # [{category_id, printer_id|null}, ...]
        updated = 0
        for row in mapping:
            cat_id = row.get('category_id')
            printer_id = row.get('printer_id')
            cat = Category.objects.filter(
                pk=cat_id, restaurant=restaurant
            ).first()
            if not cat:
                continue
            if printer_id:
                printer = KitchenPrinter.objects.filter(
                    pk=printer_id, restaurant=restaurant
                ).first()
                cat.printer = printer
            else:
                cat.printer = None
            cat.save(update_fields=['printer'])
            updated += 1
        qs = Category.objects.filter(restaurant=restaurant).order_by(
            'order', 'name'
        )
        return Response(
            {
                'updated': updated,
                'categories': CategorySerializer(qs, many=True).data,
            }
        )


class QrTableListView(APIView):
    def get(self, request):
        from tables.models import Table

        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        tables = Table.objects.filter(restaurant=restaurant).order_by('number')
        rows = []
        for t in tables:
            qr_url = ''
            if t.qr_code:
                qr_url = request.build_absolute_uri(t.qr_code.url)
            rows.append(
                {
                    'id': t.id,
                    'number': t.number,
                    'qr_enabled': t.qr_enabled,
                    'menu_url': restaurant.table_menu_url(t.number),
                    'qr_image_url': qr_url,
                    'has_qr': bool(t.qr_code),
                }
            )
        return Response(
            {
                'qr_enabled': restaurant.qr_enabled,
                'qr_design': restaurant.qr_design,
                'qr_scan_mode': restaurant.qr_scan_mode,
                'qr_menu_base_url': restaurant.qr_menu_base_url,
                'tables': rows,
            }
        )


class QrTableGenerateView(APIView):
    def post(self, request, pk):
        from tables.models import Table

        from .qr import save_table_qr

        restaurant = _restaurant(request)
        table = Table.objects.filter(pk=pk, restaurant=restaurant).first()
        if not table:
            return Response({'detail': 'Masa tapılmadı'}, status=404)
        url = save_table_qr(table, restaurant)
        return Response(
            {
                'id': table.id,
                'number': table.number,
                'menu_url': url,
                'qr_image_url': request.build_absolute_uri(table.qr_code.url),
                'has_qr': True,
                'qr_enabled': table.qr_enabled,
            }
        )


class QrTableToggleView(APIView):
    def post(self, request, pk):
        from tables.models import Table

        restaurant = _restaurant(request)
        table = Table.objects.filter(pk=pk, restaurant=restaurant).first()
        if not table:
            return Response({'detail': 'Masa tapılmadı'}, status=404)
        if 'qr_enabled' in request.data:
            table.qr_enabled = bool(request.data.get('qr_enabled'))
        else:
            table.qr_enabled = not table.qr_enabled
        table.save(update_fields=['qr_enabled'])
        return Response(
            {'id': table.id, 'number': table.number, 'qr_enabled': table.qr_enabled}
        )


class QrGenerateAllView(APIView):
    def post(self, request):
        from tables.models import Table

        from .qr import save_table_qr

        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        tables = Table.objects.filter(restaurant=restaurant)
        count = 0
        for t in tables:
            save_table_qr(t, restaurant)
            count += 1
        return Response({'ok': True, 'generated': count})


class QrBulkPdfView(APIView):
    def get(self, request):
        from django.http import HttpResponse

        from tables.models import Table

        from .qr import build_qr_pdf

        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        tables = list(
            Table.objects.filter(restaurant=restaurant, qr_enabled=True).order_by(
                'number'
            )
        )
        pdf = build_qr_pdf(tables, restaurant)
        resp = HttpResponse(pdf, content_type='application/pdf')
        resp['Content-Disposition'] = (
            f'attachment; filename="qr-{restaurant.slug}.pdf"'
        )
        return resp


class StaffListCreateView(APIView):
    def get(self, request):
        from staff.models import StaffUser
        from staff.permissions import get_request_staff, role_can_access_section
        from staff.serializers import StaffSerializer

        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        actor = get_request_staff(request)
        if actor and not role_can_access_section(actor.role, 'settings'):
            return Response({'detail': 'İcazə yoxdur'}, status=403)
        qs = StaffUser.objects.filter(restaurant=restaurant).order_by('full_name')
        return Response(StaffSerializer(qs, many=True).data)

    def post(self, request):
        from staff.models import StaffUser
        from staff.permissions import (
            can_assign_owner_role,
            get_request_staff,
            role_can_access_section,
        )
        from staff.serializers import StaffSerializer

        restaurant = _restaurant(request)
        if not restaurant:
            return Response({'detail': 'Restoran tapılmadı'}, status=404)
        actor = get_request_staff(request)
        if actor and not role_can_access_section(actor.role, 'settings'):
            return Response({'detail': 'İcazə yoxdur'}, status=403)
        role = request.data.get('role')
        if role == 'owner' and (
            not actor or not can_assign_owner_role(actor)
        ):
            return Response(
                {'detail': 'Yalnız sahib "Sahib" rolunu təyin edə bilər'},
                status=403,
            )
        ser = StaffSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        staff = ser.save(restaurant=restaurant)
        return Response(StaffSerializer(staff).data, status=201)


class StaffDetailView(APIView):
    def patch(self, request, pk):
        from staff.models import StaffUser
        from staff.permissions import (
            can_assign_owner_role,
            get_request_staff,
            role_can_access_section,
        )
        from staff.serializers import StaffSerializer

        restaurant = _restaurant(request)
        staff = StaffUser.objects.filter(pk=pk, restaurant=restaurant).first()
        if not staff:
            return Response({'detail': 'İşçi tapılmadı'}, status=404)
        actor = get_request_staff(request)
        if actor and not role_can_access_section(actor.role, 'settings'):
            return Response({'detail': 'İcazə yoxdur'}, status=403)
        new_role = request.data.get('role')
        if new_role == 'owner' and (
            not actor or not can_assign_owner_role(actor)
        ):
            return Response(
                {'detail': 'Yalnız sahib "Sahib" rolunu təyin edə bilər'},
                status=403,
            )
        ser = StaffSerializer(staff, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(StaffSerializer(staff).data)

    def delete(self, request, pk):
        from staff.models import StaffUser
        from staff.permissions import get_request_staff, role_can_access_section

        restaurant = _restaurant(request)
        staff = StaffUser.objects.filter(pk=pk, restaurant=restaurant).first()
        if not staff:
            return Response({'detail': 'İşçi tapılmadı'}, status=404)
        actor = get_request_staff(request)
        if actor and not role_can_access_section(actor.role, 'settings'):
            return Response({'detail': 'İcazə yoxdur'}, status=403)
        if staff.role == 'owner' and (
            not actor or actor.role != 'owner'
        ):
            return Response(
                {'detail': 'Sahib hesabını silmək olmaz'}, status=403
            )
        staff.delete()
        return Response(status=204)
