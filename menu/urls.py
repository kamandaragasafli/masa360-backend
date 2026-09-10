from django.urls import path

from . import views

urlpatterns = [
    path('categories/', views.CategoryListCreateView.as_view(), name='category-list'),
    path(
        'categories/reorder/',
        views.CategoryReorderView.as_view(),
        name='category-reorder',
    ),
    path(
        'categories/<int:pk>/',
        views.CategoryDetailView.as_view(),
        name='category-detail',
    ),
    path('items/', views.MenuItemListCreateView.as_view(), name='menuitem-list'),
    path('items/bulk/', views.MenuBulkUpdateView.as_view(), name='menuitem-bulk'),
    path(
        'items/<int:pk>/',
        views.MenuItemDetailView.as_view(),
        name='menuitem-detail',
    ),
    path(
        'items/<int:pk>/toggle/',
        views.MenuItemToggleView.as_view(),
        name='menuitem-toggle',
    ),
]
