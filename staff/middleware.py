"""Bearer token → request.staff_user (PIN/admin sessiya)."""


class StaffAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.staff_user = None
        request.access_token = None
        request.auth_device = None

        path = request.path or ''
        if path.startswith('/api/') and not path.startswith('/api/public/'):
            try:
                from .auth_api import get_device_from_request, get_token_from_request

                token = get_token_from_request(request)
                if token and token.staff_id:
                    request.access_token = token
                    request.staff_user = token.staff
                    request.auth_device = token.device
                else:
                    device = get_device_from_request(request)
                    if device:
                        request.auth_device = device
            except Exception:
                pass

        return self.get_response(request)
