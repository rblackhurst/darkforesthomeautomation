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

    # ── Room walkthrough (AJAX, called from pre-install page) ────────────
    path(
        "jobs/<str:invoice_number>/pre-install/rooms/add/",
        views.room_add,
        name="room_add",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/rooms/<int:room_id>/rename/",
        views.room_rename,
        name="room_rename",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/rooms/<int:room_id>/delete/",
        views.room_delete,
        name="room_delete",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/rooms/<int:room_id>/devices/add/",
        views.room_device_add,
        name="room_device_add",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/rooms/<int:room_id>/devices/<int:rd_id>/delete/",
        views.room_device_delete,
        name="room_device_delete",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/rooms/<int:room_id>/devices/<int:rd_id>/confirm/",
        views.room_device_confirm,
        name="room_device_confirm",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/rooms/<int:room_id>/devices/<int:rd_id>/swap/",
        views.room_device_swap,
        name="room_device_swap",
    ),

    # ── Internal prep ────────────────────────────────────────────────────
    path(
        "jobs/<str:invoice_number>/internal-prep/",
        views.internal_prep_render,
        name="internal_prep_render",
    ),
    path(
        "jobs/<str:invoice_number>/internal-prep/save/",
        views.internal_prep_save_field,
        name="internal_prep_save_field",
    ),
    path(
        "jobs/<str:invoice_number>/internal-prep/devices/<int:sale_line_id>/confirm/",
        views.internal_prep_confirm_device,
        name="internal_prep_confirm_device",
    ),

    # ── Pick sheet ───────────────────────────────────────────────────────
    path(
        "jobs/<str:invoice_number>/pick-sheet/",
        views.pick_sheet_render,
        name="pick_sheet_render",
    ),

    # ── Pairing sheet ────────────────────────────────────────────────────
    path(
        "jobs/<str:invoice_number>/pairing-sheet/",
        views.pairing_sheet_render,
        name="pairing_sheet_render",
    ),
    path(
        "jobs/<str:invoice_number>/pairing-sheet/row/<int:psd_id>/paired/",
        views.pairing_sheet_toggle_paired,
        name="pairing_sheet_toggle_paired",
    ),
    path(
        "jobs/<str:invoice_number>/pairing-sheet/row/<int:psd_id>/name/",
        views.pairing_sheet_save_name,
        name="pairing_sheet_save_name",
    ),
    path(
        "jobs/<str:invoice_number>/pairing-sheet/row/<int:psd_id>/notes/",
        views.pairing_sheet_save_notes,
        name="pairing_sheet_save_notes",
    ),
    path(
        "jobs/<str:invoice_number>/pairing-sheet/row/<int:psd_id>/regenerate-name/",
        views.pairing_sheet_regenerate_name,
        name="pairing_sheet_regenerate_name",
    ),
    path(
        "jobs/<str:invoice_number>/pairing-sheet/lock/",
        views.pairing_sheet_lock,
        name="pairing_sheet_lock",
    ),
    path(
        "jobs/<str:invoice_number>/pairing-sheet/unlock/",
        views.pairing_sheet_unlock,
        name="pairing_sheet_unlock",
    ),

    # ── Pre-install: custom integrations / automations + finalization ────
    path(
        "jobs/<str:invoice_number>/pre-install/job-text/",
        views.pre_install_save_job_text,
        name="pre_install_save_job_text",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/finalize/",
        views.pre_install_finalize,
        name="pre_install_finalize",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/payment-received/",
        views.pre_install_payment_received,
        name="pre_install_payment_received",
    ),
    path(
        "jobs/<str:invoice_number>/pre-install/invoice-sent/",
        views.pre_install_toggle_invoice_sent,
        name="pre_install_toggle_invoice_sent",
    ),
    path(
        "jobs/<str:invoice_number>/edit-sale/",
        views.sales_form_edit,
        name="sales_form_edit",
    ),
]
