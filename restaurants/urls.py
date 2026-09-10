from django.urls import path

from .attention import DashboardAttentionView
from .dashboard_home import DashboardHomeView
from .views import (
    CategoryPrinterMapView,
    CurrentRestaurantView,
    KitchenPrinterDetailView,
    KitchenPrinterListCreateView,
    KitchenPrinterTestView,
    QrBulkPdfView,
    QrGenerateAllView,
    QrTableGenerateView,
    QrTableListView,
    QrTableToggleView,
    StaffDetailView,
    StaffListCreateView,
)

urlpatterns = [
    path('current/', CurrentRestaurantView.as_view(), name='restaurant-current'),
    path(
        'dashboard/attention/',
        DashboardAttentionView.as_view(),
        name='dashboard-attention',
    ),
    path(
        'dashboard/home/',
        DashboardHomeView.as_view(),
        name='dashboard-home',
    ),
    path(
        'printers/',
        KitchenPrinterListCreateView.as_view(),
        name='printer-list',
    ),
    path(
        'printers/<int:pk>/',
        KitchenPrinterDetailView.as_view(),
        name='printer-detail',
    ),
    path(
        'printers/<int:pk>/test/',
        KitchenPrinterTestView.as_view(),
        name='printer-test',
    ),
    path(
        'category-printers/',
        CategoryPrinterMapView.as_view(),
        name='category-printers',
    ),
    path('qr/tables/', QrTableListView.as_view(), name='qr-tables'),
    path(
        'qr/tables/<int:pk>/generate/',
        QrTableGenerateView.as_view(),
        name='qr-generate',
    ),
    path(
        'qr/tables/<int:pk>/toggle/',
        QrTableToggleView.as_view(),
        name='qr-toggle',
    ),
    path('qr/generate-all/', QrGenerateAllView.as_view(), name='qr-generate-all'),
    path('qr/bulk-pdf/', QrBulkPdfView.as_view(), name='qr-bulk-pdf'),
    path('staff/', StaffListCreateView.as_view(), name='staff-list'),
    path('staff/<int:pk>/', StaffDetailView.as_view(), name='staff-detail'),
]
