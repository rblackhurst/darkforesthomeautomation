"""
URL configuration for the portal subdomain (portal.darkforesthomeautomation.com).
Set as request.urlconf by SubdomainRoutingMiddleware for that host.
"""
from django.http import HttpResponse
from django.urls import include, path


def health(request):
    return HttpResponse("ok\n", content_type="text/plain; charset=utf-8")


urlpatterns = [
    path("_health/", health, name="health"),
    path("", include("client_hub.urls")),
]
