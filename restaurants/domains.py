"""Restoran domeni — normalize + Host üzrə tapma."""

from __future__ import annotations

import re

from django.conf import settings

from restaurants.models import Restaurant

# Platform hostları — burada Landing göstərilir, restoran saytı yox
_DEFAULT_PLATFORM = (
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    'surfua.az',
    'www.surfua.az',
    'app.surfua.az',
    'panel.surfua.az',
)


def platform_hosts() -> set[str]:
    extra = getattr(settings, 'PLATFORM_HOSTS', '') or ''
    hosts = set(_DEFAULT_PLATFORM)
    for part in str(extra).split(','):
        h = normalize_domain(part)
        if h:
            hosts.add(h)
    return hosts


def normalize_domain(raw: str) -> str:
    """thedöner.az / https://www.X.az:443/path → punycode host."""
    d = (raw or '').strip().lower()
    d = d.replace('https://', '').replace('http://', '')
    d = d.split('/')[0].split('?')[0].split('#')[0]
    if d.count(':') == 1 and not d.startswith('['):
        d = d.rsplit(':', 1)[0]
    if d.startswith('www.'):
        d = d[4:]
    if not d or ' ' in d or '.' not in d:
        return ''
    # IDN (ö, ə və s.) → punycode; ASCII olduğu kimi qalır
    try:
        return d.encode('idna').decode('ascii')
    except Exception:
        return ''


def is_platform_host(host: str) -> bool:
    h = normalize_domain(host)
    if not h:
        return True
    if h in platform_hosts():
        return True
    # LAN — panel/dev
    if h.startswith('192.168.') or h.startswith('10.'):
        return True
    if re.match(r'^172\.(1[6-9]|2\d|3[0-1])\.', h):
        return True
    return False


def request_host(request) -> str:
    forwarded = (request.META.get('HTTP_X_FORWARDED_HOST') or '').split(',')[0]
    raw = forwarded.strip() or request.META.get('HTTP_HOST') or ''
    return normalize_domain(raw)


def resolve_by_domain(domain: str) -> Restaurant | None:
    d = normalize_domain(domain)
    if not d or is_platform_host(d):
        return None
    return (
        Restaurant.objects.filter(custom_domain=d, is_active=True)
        .exclude(custom_domain='')
        .first()
    )


def storefront_base_url(restaurant: Restaurant) -> str:
    """Müştəri saytının bazası — əvvəl öz domen, sonra LAN/slug."""
    domain = normalize_domain(getattr(restaurant, 'custom_domain', '') or '')
    if domain:
        return f'https://{domain}'
    from django.conf import settings as dj

    base = (restaurant.qr_menu_base_url or '').strip().rstrip('/')
    if base:
        return base
    return getattr(dj, 'PUBLIC_MENU_BASE', 'http://127.0.0.1:5173').rstrip('/')
