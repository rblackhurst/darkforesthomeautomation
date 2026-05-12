from django.contrib import admin
from django.http import HttpResponse
from django.urls import path


def home(request):
    return HttpResponse(
        "Dark Forest Home Automation\n"
        "App online. Deployment pipeline verified.\n",
        content_type="text/plain; charset=utf-8",
    )


urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
]
