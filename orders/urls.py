from django.urls import path

from .history import (
    HistoryDetailView,
    HistoryExportExcelView,
    HistoryListView,
    HistoryStatsView,
    OrderCancelView,
)
from .kanban import KanbanBoardView
from .reports import (
    ReportFinanceExportView,
    ReportOpsView,
    ReportOverviewView,
    ReportProductsView,
    ReportSalesView,
)
from .views import (
    KitchenOrderListView,
    OrderAdvanceView,
    OrderCreateView,
    PrintJobListView,
    PrintJobRetryView,
)

urlpatterns = [
    path('', OrderCreateView.as_view(), name='order-create'),
    path('kitchen/', KitchenOrderListView.as_view(), name='kitchen-orders'),
    path('kanban/', KanbanBoardView.as_view(), name='orders-kanban'),
    path('history/', HistoryListView.as_view(), name='history-list'),
    path('history/stats/', HistoryStatsView.as_view(), name='history-stats'),
    path(
        'history/export.xlsx',
        HistoryExportExcelView.as_view(),
        name='history-export',
    ),
    path(
        'history/<int:pk>/',
        HistoryDetailView.as_view(),
        name='history-detail',
    ),
    path('reports/overview/', ReportOverviewView.as_view(), name='report-overview'),
    path('reports/sales/', ReportSalesView.as_view(), name='report-sales'),
    path('reports/products/', ReportProductsView.as_view(), name='report-products'),
    path('reports/ops/', ReportOpsView.as_view(), name='report-ops'),
    path(
        'reports/export.xlsx',
        ReportFinanceExportView.as_view(),
        name='report-export',
    ),
    path('print-jobs/', PrintJobListView.as_view(), name='print-jobs'),
    path(
        'print-jobs/<int:pk>/retry/',
        PrintJobRetryView.as_view(),
        name='print-job-retry',
    ),
    path(
        '<int:pk>/advance/',
        OrderAdvanceView.as_view(),
        name='order-advance',
    ),
    path(
        '<int:pk>/cancel/',
        OrderCancelView.as_view(),
        name='order-cancel',
    ),
]
