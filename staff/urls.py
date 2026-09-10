from django.urls import path

from .auth_api import (
    AdminLoginView,
    DeleteAccountView,
    DevicePairView,
    DeviceStaffListView,
    LogoutView,
    MeView,
    MobileLoginView,
    MobileStaffListView,
    PinLoginView,
    RegisterView,
    SubscribeView,
    SwitchStaffView,
)

urlpatterns = [
    path('admin/login/', AdminLoginView.as_view(), name='auth-admin-login'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('subscribe/', SubscribeView.as_view(), name='auth-subscribe'),
    path('device/pair/', DevicePairView.as_view(), name='auth-device-pair'),
    path('device/staff/', DeviceStaffListView.as_view(), name='auth-device-staff'),
    path('pin/', PinLoginView.as_view(), name='auth-pin'),
    path('mobile/staff/', MobileStaffListView.as_view(), name='auth-mobile-staff'),
    path('mobile/login/', MobileLoginView.as_view(), name='auth-mobile-login'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('switch/', SwitchStaffView.as_view(), name='auth-switch'),
    path('account/delete/', DeleteAccountView.as_view(), name='auth-account-delete'),
]
