from django.urls import path

from . import views

urlpatterns = [
    path('auth/login/', views.CourierLoginView.as_view(), name='courier-login'),
    path('auth/staff/', views.CourierStaffListView.as_view(), name='courier-staff'),
    path('me/', views.CourierMeView.as_view(), name='courier-me'),
    path(
        'availability/',
        views.CourierAvailabilityView.as_view(),
        name='courier-availability',
    ),
    path('location/', views.CourierLocationView.as_view(), name='courier-location'),
    path(
        'offers/<int:pk>/accept/',
        views.OfferAcceptView.as_view(),
        name='courier-offer-accept',
    ),
    path(
        'offers/<int:pk>/reject/',
        views.OfferRejectView.as_view(),
        name='courier-offer-reject',
    ),
    path(
        'assignments/<int:pk>/pickup/',
        views.AssignmentPickupView.as_view(),
        name='courier-pickup',
    ),
    path(
        'assignments/<int:pk>/deliver/',
        views.AssignmentDeliverView.as_view(),
        name='courier-deliver',
    ),
    path('earnings/', views.EarningsView.as_view(), name='courier-earnings'),
    path('demo/offer/', views.DemoOfferView.as_view(), name='courier-demo-offer'),
]
