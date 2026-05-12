from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def health(request):
    # Plain-text health check for deployment verification. Unauthenticated.
    return HttpResponse("ok\n", content_type="text/plain; charset=utf-8")


urlpatterns = [
    path("_health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("", include("jobs.urls")),
]
