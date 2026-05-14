from django.shortcuts import redirect
from django.urls import resolve, reverse

from .models import EmployeeTOTP


class Require2FAMiddleware:
    """Force any logged-in staff user to enrol TOTP before using the app.

    Active when `user.is_staff` is True and they have no confirmed TOTP.
    Skips:
      - anonymous users (handled by the per-view @login_required)
      - the accounts namespace (login, setup, verify, logout, codes)
      - the admin's own login/logout views (so superusers can still recover
        via /admin/login/ when their session is broken)
      - the health check
    """

    EXEMPT_URL_PREFIXES = (
        "/_health/",
        "/admin/login/",
        "/admin/logout/",
        "/static/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not self._needs_redirect(request):
            return self.get_response(request)
        return redirect(reverse("accounts:two_factor_setup"))

    def _needs_redirect(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        if not user.is_staff:
            return False

        path = request.path
        if any(path.startswith(p) for p in self.EXEMPT_URL_PREFIXES):
            return False
        try:
            match = resolve(path)
        except Exception:
            return False
        if match.app_name == "accounts":
            return False

        totp = EmployeeTOTP.objects.filter(user=user).first()
        return totp is None or not totp.is_confirmed
