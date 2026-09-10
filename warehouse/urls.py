from django.urls import path

from .views import (
    BatchReceiveView,
    IngredientCategoryListView,
    IngredientListView,
    WarehouseAlertsView,
    WasteCreateView,
)

urlpatterns = [
    path('alerts/', WarehouseAlertsView.as_view(), name='warehouse-alerts'),
    path(
        'categories/',
        IngredientCategoryListView.as_view(),
        name='warehouse-categories',
    ),
    path(
        'ingredients/',
        IngredientListView.as_view(),
        name='warehouse-ingredients',
    ),
    path('receive/', BatchReceiveView.as_view(), name='warehouse-receive'),
    path('waste/', WasteCreateView.as_view(), name='warehouse-waste'),
]
