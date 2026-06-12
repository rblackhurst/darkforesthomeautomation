from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def health(request):
    # Plain-text health check for deployment verification. Unauthenticated.
    return HttpResponse("ok\n", content_type="text/plain; charset=utf-8")


urlpatterns = [
    path("_health/", health, name="health"),
    path("admin/credentials/", include("client_credentials.urls")),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("webhooks/", include("stripe_integration.urls")),
    # jobs must come before client_hub so that the root '/' resolves to the
    # staff dashboard on the admin subdomain and in tests (testserver host).
    # On portal.darkforesthomeautomation.com the middleware sets request.urlconf
    # to dfha.urls_portal, which only includes client_hub — jobs never applies there.
    path("", include("jobs.urls")),
    path("", include("client_hub.urls")),
]
