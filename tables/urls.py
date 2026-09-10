from django.urls import path

from .views import (
    FloorPlanView,
    ReservationCreateView,
    TableActionView,
    TableDetailView,
    TableListView,
)

urlpatterns = [
    path('', TableListView.as_view(), name='table-list'),
    path('floor/', FloorPlanView.as_view(), name='floor-plan'),
    path('reservations/', ReservationCreateView.as_view(), name='reservation-create'),
    path('<int:pk>/', TableDetailView.as_view(), name='table-detail'),
    path('<int:pk>/actions/', TableActionView.as_view(), name='table-action'),
]
