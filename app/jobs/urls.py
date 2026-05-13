from django.urls import path

from . import views


app_name = "jobs"

urlpatterns = [
    path("", views.home_dashboard, name="home"),
    path("jobs/new/", views.sales_form, name="sales_form"),

    # ── Backend install ──────────────────────────────────────────────────
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

    # ── Pre-install checklist ────────────────────────────────────────────
    path(
        "jobs/<str:invoice_number>/pre-install/",
        views.pre_install_checklist_render,
        name="pre_install_checklist_render",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/item/<int:item_id>/check/",
        views.pre_install_toggle_check,
        name="pre_install_toggle_check",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/item/<int:item_id>/notes/",
        views.pre_install_save_notes,
        name="pre_install_save_notes",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/capture/<slug:key>/",
        views.pre_install_save_capture,
        name="pre_install_save_capture",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/reset/",
        views.pre_install_reset,
        name="pre_install_reset",
    ),
]
