from django.urls import path

from . import views


app_name = "jobs"

urlpatterns = [
    path("", views.home_dashboard, name="home"),
    path(
        "jobs/<str:invoice_number>/backend-install/",
        views.backend_install_render,
        name="backend_install_render",
    ),
    path(
        "jobs/<str:invoice_number>/backend-install/item/<int:item_id>/check/",
        views.backend_install_toggle_check,
        name="backend_install_toggle_check",
    ),
    path(
        "jobs/<str:invoice_number>/backend-install/item/<int:item_id>/notes/",
        views.backend_install_save_notes,
        name="backend_install_save_notes",
    ),
    path(
        "jobs/<str:invoice_number>/backend-install/capture/<slug:key>/",
        views.backend_install_save_capture,
        name="backend_install_save_capture",
    ),
    path(
        "jobs/<str:invoice_number>/backend-install/reset/",
        views.backend_install_reset,
        name="backend_install_reset",
    ),
]
