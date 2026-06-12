from django.http import Http404

_ADMIN_HOST = 'app.darkforesthomeautomation.com'
_PORTAL_HOST = 'portal.darkforesthomeautomation.com'

# Paths accessible on the admin subdomain outside the /admin/ prefix.
# /webhooks/ — Stripe posts to app.darkforesthomeautomation.com; must stay reachable.
# /credentials/ — Phase 4 admin credential detail views (staff-only, no /admin prefix).
_ADMIN_ALLOWED_PREFIXES = (
    '/admin',
    '/accounts',
    '/_health',
    '/webhooks',
    '/static',
    '/credentials',
)


class SubdomainRoutingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0]

        if host == _PORTAL_HOST:
            # Give the portal subdomain its own URL configuration so that:
            # - client_hub URLs are available at root level
            # - staff/admin URLs are completely absent (naturally 404, not blocked)
            # This also means reverse() within portal requests uses urls_portal.
            request.urlconf = 'dfha.urls_portal'
            # Belt-and-suspenders: block /admin explicitly even though it's not
            # in urls_portal, in case of future URL conf drift.
            if request.path.startswith('/admin'):
                raise Http404

        elif host == _ADMIN_HOST:
            # Block Client Hub URLs on the admin subdomain.
            # client_hub URLs share the root prefix with jobs, so an explicit
            # allowlist is needed — any path not on this list is a client_hub route.
            if not any(request.path.startswith(p) for p in _ADMIN_ALLOWED_PREFIXES):
                raise Http404

        return self.get_response(request)
