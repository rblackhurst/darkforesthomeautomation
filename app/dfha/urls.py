from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from django_otp.admin import OTPAdminSite


# Require a verified OTP device to reach the Django admin. Password alone is
# not enough; staff must also pass an authenticator-app challenge.
admin.site.__class__ = OTPAdminSite


def health(request):
    # Plain-text health check for deployment verification. Unauthenticated.
    return HttpResponse("ok\n", content_type="text/plain; charset=utf-8")


urlpatterns = [
    path("_health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("", include("jobs.urls")),
]
