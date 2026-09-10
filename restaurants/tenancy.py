"""Multi-tenant restoran seçimi — token, domain, slug."""

from __future__ import annotations

from restaurants.domains import normalize_domain, request_host, resolve_by_domain
from restaurants.models import Restaurant


def resolve_restaurant(request, *, allow_slug: bool = True):
    """
    Authenticated sorğularda həmişə token-dakı restoran.
    Public: domain (Host) → slug / restaurant id.
    """
    try:
        from staff.auth_api import get_token_from_request

        token = get_token_from_request(request)
        if token and token.restaurant_id:
            return token.restaurant
    except Exception:
        pass

    if not allow_slug:
        return None

    data = getattr(request, 'data', {}) or {}
    params = getattr(request, 'query_params', {}) or {}

    restaurant_id = params.get('restaurant') or data.get('restaurant')
    if restaurant_id:
        return Restaurant.objects.filter(pk=restaurant_id).first()

    domain = (
        params.get('domain')
        or data.get('domain')
        or params.get('host')
        or data.get('host')
        or ''
    ).strip()
    if domain:
        found = resolve_by_domain(domain)
        if found:
            return found

    # Host header (öz domenlə gələn public API)
    host = request_host(request)
    if host:
        found = resolve_by_domain(host)
        if found:
            return found

    slug = (params.get('slug') or data.get('slug') or '').strip()
    if slug:
        return Restaurant.objects.filter(slug=slug).first()

    return None
