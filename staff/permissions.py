"""
Rol matrisi — ekran girişi (v1) + əməliyyat icazə helper-ləri (v2 hazırlığı).

Prinsip:
  rol  = hansı ekranlara giriş
  icazə = ekran daxilində nə edə bilər (boolean override + rol default)
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

# Bölmə → frontend marşrut
SECTION_ROUTE = {
    'dashboard': '/home',
    'tables': '/table',
    'menu': '/menu',
    'orders': '/order',
    'board': '/board',
    'kitchen': '/kitchen',
    'history': '/history',
    'reports': '/report',
    'settings': '/settings',
    'alerts': '/alert',
    'warehouse': '/warehouse',
    # Gələcək:
    # 'courier': '/courier',
}

# Rol → açıq bölmələr (matris v1 — "baxış" belə giriş sayılır)
ROLE_SECTIONS = {
    'owner': [
        'dashboard',
        'tables',
        'menu',
        'orders',
        'board',
        'kitchen',
        'history',
        'reports',
        'settings',
        'alerts',
        'warehouse',
    ],
    'manager': [
        'dashboard',
        'tables',
        'menu',
        'orders',
        'board',
        'kitchen',
        'history',
        'reports',
        'settings',
        'alerts',
        'warehouse',
    ],
    'waiter': ['tables', 'menu', 'orders', 'board', 'alerts'],
    'cashier': ['tables', 'menu', 'orders', 'board', 'history', 'alerts'],
    'kitchen': ['menu', 'board', 'kitchen', 'alerts'],
    'warehouse': ['warehouse', 'alerts'],
    'courier': ['alerts'],
}

ROLE_HOME = {
    'owner': '/home',
    'manager': '/home',
    'waiter': '/order',
    'cashier': '/order?mode=quick',
    'kitchen': '/kitchen',
    'warehouse': '/warehouse',
    'courier': '/alert',
}

# Ayarlar tab-ları (ekran daxilində məhdudiyyət — yüngül v1)
SETTINGS_TABS = {
    'owner': [
        'profile',
        'qr',
        'site',
        'payment',
        'staff',
        'notify',
        'printers',
        'delivery',
        'lang',
        'account',
    ],
    'manager': ['qr', 'site', 'printers', 'staff', 'account'],
}

# Hesabat tab-ları (menecer: işçi performansı gizlədiləcək — v2)
REPORT_TABS = {
    'owner': ['finance', 'sales', 'products', 'ops'],
    'manager': ['finance', 'sales', 'products'],  # ops/staff performance yox
}

ADMIN_ROLES = frozenset({'owner', 'manager'})


def sections_for_role(role: str) -> list[str]:
    return list(ROLE_SECTIONS.get(role, []))


def routes_for_role(role: str) -> list[str]:
    return [
        SECTION_ROUTE[s]
        for s in sections_for_role(role)
        if s in SECTION_ROUTE
    ]


def home_for_role(role: str) -> str:
    return ROLE_HOME.get(role, '/login')


def role_can_access_section(role: str, section: str) -> bool:
    return section in ROLE_SECTIONS.get(role, [])


def role_can_access_path(role: str, pathname: str) -> bool:
    path = (pathname or '/').split('?')[0] or '/'
    for section, route in SECTION_ROUTE.items():
        if section not in ROLE_SECTIONS.get(role, []):
            continue
        if path == route or path.startswith(f'{route}/'):
            return True
    return False


# --- Əməliyyat səviyyəsi (default rol + boolean override) — UI v2 ---


def can_apply_discount(staff) -> bool:
    if not staff:
        return False
    if staff.role in ADMIN_ROLES:
        return True
    return bool(getattr(staff, 'can_discount', False))


def can_edit_menu_prices(staff) -> bool:
    if not staff:
        return False
    if staff.role in ADMIN_ROLES:
        return True
    return bool(getattr(staff, 'can_edit_menu', False))


def can_cancel_preparing_order(staff) -> bool:
    if not staff:
        return False
    if staff.role in ADMIN_ROLES:
        return True
    return bool(getattr(staff, 'can_cancel_preparing_order', False))


def can_assign_owner_role(staff) -> bool:
    return bool(staff and staff.role == 'owner')


def settings_tabs_for(staff) -> list[str]:
    if not staff:
        return []
    return list(SETTINGS_TABS.get(staff.role, []))


def report_tabs_for(staff) -> list[str]:
    if not staff:
        return []
    return list(REPORT_TABS.get(staff.role, []))


def get_request_staff(request):
    staff = getattr(request, 'staff_user', None)
    if staff is not None:
        return staff
    django_req = getattr(request, '_request', None)
    if django_req is not None:
        return getattr(django_req, 'staff_user', None)
    return None


class HasRolePermission(BasePermission):
    """
    View-də `access_key = 'kitchen'` və ya `access_keys = ['orders', 'pos']`.
    """

    message = 'Bu bölməyə giriş icazəniz yoxdur'

    def has_permission(self, request, view):
        staff = get_request_staff(request)
        if staff is None or not staff.is_active:
            return False
        keys = getattr(view, 'access_keys', None)
        if keys is None:
            key = getattr(view, 'access_key', None)
            keys = [key] if key else []
        if not keys:
            return True
        return any(role_can_access_section(staff.role, k) for k in keys)
