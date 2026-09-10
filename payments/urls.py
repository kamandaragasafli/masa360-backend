from django.urls import path

from . import views
from .pos import PosCheckoutView, PosOpenChecksView

urlpatterns = [
    path('create/', views.CreatePaymentView.as_view(), name='payment-create'),
    path('pos/checkout/', PosCheckoutView.as_view(), name='pos-checkout'),
    path('pos/open/', PosOpenChecksView.as_view(), name='pos-open-checks'),
    path(
        '<int:pk>/',
        views.PaymentStatusView.as_view(),
        name='payment-status',
    ),
    path(
        'order/<int:order_id>/',
        views.OrderPaymentStatusView.as_view(),
        name='order-payment-status',
    ),
    path(
        'webhook/<str:gateway>/',
        views.payment_webhook,
        name='payment-webhook',
    ),
    path(
        'mock-pay/<str:invoice_id>/',
        views.mock_pay_page,
        name='payment-mock-pay',
    ),
    path(
        'expire-pending/',
        views.ExpirePaymentsView.as_view(),
        name='payment-expire',
    ),
]
