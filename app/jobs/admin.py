from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html, mark_safe

from client_credentials.models import CredentialDeletionRequest, InstalledSystem as InstalledClientSystem

from .models import (
    AuditLogEntry,
    AutomationConfig,
    BackendInstall,
    BackendInstallCapture,
    BackendInstallItemState,
    CatalogDevice,
    ChecklistItem,
    ChecklistStep,
    ChecklistTemplate,
    CredentialBundle,
    Customer,
    InternalPrep,
    Job,
    OnsiteInstall,
    Package,
    PackageDevice,
    PairingSheet,
    PairingSheetDevice,
    PreInstallCapture,
    PreInstallChecklist,
    PreInstallItemState,
    Property,
    Room,
    RoomDevice,
    SaleLine,
    TroubleRequest,
    WalkthroughSignoff,
    _fmt_order,
)


class PreInstallChecklistInline(admin.StackedInline):
    model = PreInstallChecklist
    extra = 0
    can_delete = False


class BackendInstallInline(admin.StackedInline):
    model = BackendInstall
    extra = 0
    can_delete = False


class PairingSheetInline(admin.StackedInline):
    model = PairingSheet
    extra = 0
    can_delete = False
    readonly_fields = ("locked", "locked_at", "locked_by")


class PairingSheetDeviceInline(admin.TabularInline):
    model = PairingSheetDevice
    extra = 0
    fields = ("room_device", "instance_index", "ha_name", "paired", "paired_at", "paired_by", "notes")
    readonly_fields = ("paired_at", "paired_by")
    raw_id_fields = ("room_device",)


@admin.register(PairingSheet)
class PairingSheetAdmin(admin.ModelAdmin):
    list_display = ("job", "locked", "locked_at", "completed_at", "updated_at")
    list_filter = ("locked",)
    search_fields = ("job__invoice_number", "job__customer__last_name")
    readonly_fields = ("created_at", "updated_at", "locked_at", "locked_by", "completed_at")
    inlines = [PairingSheetDeviceInline]


class AutomationConfigInline(admin.StackedInline):
    model = AutomationConfig
    extra = 0
    can_delete = False


class OnsiteInstallInline(admin.StackedInline):
    model = OnsiteInstall
    extra = 0
    can_delete = False


class WalkthroughSignoffInline(admin.StackedInline):
    model = WalkthroughSignoff
    extra = 0
    can_delete = False


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    fields = ("device", "quantity", "unit_cost", "confirmed_in_stock", "notes", "sort_order")
    ordering = ("sort_order", "id")


class InstalledSystemInline(admin.StackedInline):
    model = InstalledClientSystem
    extra = 0
    show_change_link = True
    fields = [
        'system_type', 'name', 'manufacturer', 'job', 'notes',
        'is_visible', 'credential_summary_col', 'device_summary_col',
    ]
    readonly_fields = ['credential_summary_col', 'device_summary_col']

    @admin.display(description='Credentials')
    def credential_summary_col(self, obj):
        if obj.pk is None:
            return '—'
        count = obj.credentials.filter(is_visible=True).count()
        if count == 0:
            return 'No platform credentials'
        change_url = reverse('admin:client_credentials_installedsystem_change', args=[obj.pk])
        return format_html(
            '{} platform credential{} &mdash; <a href="{}">&#8594; View in Credentials</a>',
            count, 's' if count != 1 else '', change_url,
        )

    @admin.display(description='Devices')
    def device_summary_col(self, obj):
        if obj.pk is None:
            return '—'
        count = obj.devices.filter(is_visible=True).count()
        if count == 0:
            return 'No devices'
        change_url = reverse('admin:client_credentials_installedsystem_change', args=[obj.pk])
        return format_html(
            '{} device{} &mdash; <a href="{}">&#8594; View in Credentials</a>',
            count, 's' if count != 1 else '', change_url,
        )


class CredentialDeletionRequestInline(admin.StackedInline):
    model = CredentialDeletionRequest
    extra = 0
    show_change_link = True
    fields = [
        'status', 'requested_at', 'requested_by', 'scope_notes',
        'staff_assigned', 'staff_notes', 're_onboarding_fee_disclosed', 'resolved_at',
    ]
    readonly_fields = ['requested_at']


_SUB_STATUS_STYLES = {
    'active': 'color:#2e7d32;font-weight:bold',
    'past_due': 'color:#e65100;font-weight:bold',
    'canceled': 'color:#666',
    'cancelled': 'color:#666',
    'unpaid': 'color:#c62828;font-weight:bold',
    'trialing': 'color:#1565c0',
}


class PropertyInline(admin.StackedInline):
    model = Property
    extra = 0
    show_change_link = True
    fields = [
        'name', 'address_line1', 'address_line2', 'city', 'state',
        'postal_code', 'notes', 'subscription_status_col',
        'service_plan_tier', 'billing_interval',
    ]
    readonly_fields = ['subscription_status_col']

    @admin.display(description='Subscription status')
    def subscription_status_col(self, obj):
        if not obj.pk or not obj.subscription_status:
            return '—'
        style = _SUB_STATUS_STYLES.get(obj.subscription_status, 'color:#666')
        label = obj.subscription_status.replace('_', ' ').title()
        return format_html('<span style="{}">{}</span>', style, label)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "email", "property_count_col", "pending_deletion_col")
    search_fields = ("last_name", "first_name", "email", "phone")
    inlines = [PropertyInline, CredentialDeletionRequestInline]

    @admin.display(description='Properties')
    def property_count_col(self, obj):
        count = obj.properties.count()
        if count == 0:
            return 'No properties'
        return f'{count} propert{"ies" if count != 1 else "y"}'

    @admin.display(description='Deletion requests')
    def pending_deletion_col(self, obj):
        if obj.deletion_requests.filter(status='pending').exists():
            return format_html(
                '<span style="color:#c62828;font-weight:bold">&#9888; Pending deletion request</span>'
            )
        return '—'


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ['name', 'customer', 'city', 'state', 'service_tier_col', 'subscription_status']
    list_filter = ['service_plan_tier', 'subscription_status', 'state']
    search_fields = ['name', 'customer__last_name', 'customer__first_name', 'address_line1']
    autocomplete_fields = ['customer']
    inlines = [InstalledSystemInline]
    fieldsets = (
        (None, {
            'fields': ('customer', 'name', 'address_line1', 'address_line2', 'city', 'state', 'postal_code', 'notes')
        }),
        ('Subscription Status', {
            'fields': ('stripe_subscription_status_panel',),
            'classes': ('collapse',),
            'description': 'Current service plan subscription from Stripe.',
        }),
    )
    readonly_fields = ['stripe_subscription_status_panel']

    @admin.display(description="Service tier", ordering="service_plan_tier")
    def service_tier_col(self, obj):
        return obj.get_service_plan_tier_display()

    @admin.display(description="Subscription")
    def stripe_subscription_status_panel(self, obj):
        if not obj.stripe_subscription_id:
            return "No active subscription."

        _ID = 'font-family:monospace;font-size:0.85em;color:#666'
        _TD = 'padding:6px 4px'
        _GREY = 'color:#666'

        rows = []

        # Service Plan
        tier_display = obj.get_service_plan_tier_display()
        if not obj.service_plan_tier or obj.service_plan_tier == 'none':
            plan_cell = format_html('<span style="{}">{}</span>', _GREY, tier_display)
        else:
            plan_cell = mark_safe(tier_display)
        rows.append(format_html(
            '<tr><td style="{td}"><strong>Service Plan</strong></td><td style="{td}">{v}</td></tr>',
            td=_TD, v=plan_cell,
        ))

        # Status
        sub_status = obj.subscription_status or ''
        status_style = _SUB_STATUS_STYLES.get(sub_status, '')
        if status_style:
            status_cell = format_html('<span style="{}">{}</span>', status_style, sub_status.replace('_', ' ').title())
        else:
            status_cell = format_html('<span style="{}">{}</span>', _ID, sub_status)
        rows.append(format_html(
            '<tr><td style="{td}"><strong>Status</strong></td><td style="{td}">{v}</td></tr>',
            td=_TD, v=status_cell,
        ))

        # Billing Interval
        rows.append(format_html(
            '<tr><td style="{td}"><strong>Billing</strong></td><td style="{td}">{v}</td></tr>',
            td=_TD, v=obj.get_billing_interval_display(),
        ))

        # Subscription ID
        rows.append(format_html(
            '<tr><td style="{td}"><strong>Subscription ID</strong></td>'
            '<td style="{td}"><span style="{id}">{v}</span></td></tr>',
            td=_TD, id=_ID, v=obj.stripe_subscription_id,
        ))

        return mark_safe(
            '<table style="border-collapse:collapse;width:100%">'
            + "".join(rows)
            + "</table>"
        )


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("invoice_label_col", "customer", "status", "install_date", "finalized_at", "is_locked")
    list_filter = ("status", "install_date", "deposit_paid", "final_paid", "payment_override")
    search_fields = ("invoice_number", "display_invoice_number", "customer__last_name", "customer__first_name")
    autocomplete_fields = ("customer", "package", "property")
    date_hierarchy = "install_date"
    readonly_fields = (
        "invoice_number",
        "display_invoice_number",
        "finalized_at",
        "payment_received_at",
        "install_links",
        "stripe_payment_status_panel",
    )
    inlines = [
        SaleLineInline,
        PreInstallChecklistInline,
        BackendInstallInline,
        PairingSheetInline,
        AutomationConfigInline,
        OnsiteInstallInline,
        WalkthroughSignoffInline,
    ]

    fieldsets = (
        (None, {
            "fields": (
                "invoice_number", "display_invoice_number", "customer", "property", "package", "status",
                "sold_on", "install_date",
                "package_summary", "notes",
                "custom_integrations", "custom_automations",
            ),
        }),
        ("Payment", {
            "fields": ("finalized_at", "payment_override", "payment_override_amount", "payment_received", "payment_received_at"),
            "classes": ("collapse",),
        }),
        ("Stripe Payment Status", {
            "fields": ("stripe_payment_status_panel",),
            "classes": ("collapse",),
            "description": "Live payment status from Stripe. Open Stripe Dashboard for real-time detail.",
        }),
        ("Install forms", {
            "fields": ("install_links",),
            "description": "Open a fillable form for this job.",
        }),
    )

    @admin.display(description="Invoice", ordering="display_invoice_number")
    def invoice_label_col(self, obj):
        return obj.display_invoice_number or f"[draft {obj.invoice_number[-8:]}]"

    @admin.display(description="Open")
    def install_links(self, obj):
        if not obj.pk:
            return "Save the job first to enable form links."
        btn = (
            'display:inline-block;padding:6px 14px;background:#2d6b4e;'
            'color:#fff;border-radius:4px;text-decoration:none;font-weight:500;margin-right:8px;'
        )
        pi_url = reverse("jobs:pre_install_checklist_render", args=[obj.invoice_number])
        bi_url = reverse("jobs:backend_install_render", args=[obj.invoice_number])
        return format_html(
            '<a class="button" href="{}" target="_blank" rel="noopener" style="{}">'
            'Pre-install checklist →</a>'
            '<a class="button" href="{}" target="_blank" rel="noopener" style="{}">'
            'Backend install →</a>',
            pi_url, btn,
            bi_url, btn,
        )

    @admin.display(description="Payment status")
    def stripe_payment_status_panel(self, obj):
        _ID = 'font-family:monospace;font-size:0.85em;color:#666'
        _GREEN = 'color:#2e7d32;font-weight:bold'
        _RED = 'color:#c62828'
        _RED_BOLD = 'color:#c62828;font-weight:bold'
        _TD = 'padding:6px 4px'

        has_data = any([
            obj.stripe_deposit_invoice_id,
            obj.stripe_final_invoice_url,
            obj.stripe_final_invoice_id,
            obj.stripe_deposit_invoice_url,
            obj.stripe_quote_id,
            obj.deposit_paid,
            obj.final_paid,
            obj.payment_failed,
        ])
        if not has_data:
            return "No Stripe payment activity recorded for this job."

        rows = []

        # Deposit Invoice
        dep_status = format_html('<span style="{}">{}</span>',
                                 _GREEN if obj.deposit_paid else _RED,
                                 "Paid" if obj.deposit_paid else "Unpaid")
        dep_link = (format_html('<a href="{}" target="_blank" rel="noopener">Open in Stripe ↗</a>',
                                obj.stripe_deposit_invoice_url)
                    if obj.stripe_deposit_invoice_url else "—")
        dep_id = (format_html(' <span style="{}">{}</span>', _ID, obj.stripe_deposit_invoice_id)
                  if obj.stripe_deposit_invoice_id else "")
        rows.append(format_html(
            '<tr><td style="{td}"><strong>Deposit Invoice</strong></td>'
            '<td style="{td}">{status}</td>'
            '<td style="{td}">{link}{id}</td></tr>',
            td=_TD, status=dep_status, link=dep_link, id=dep_id,
        ))

        # Final Invoice
        fin_status = format_html('<span style="{}">{}</span>',
                                 _GREEN if obj.final_paid else _RED,
                                 "Paid" if obj.final_paid else "Unpaid")
        fin_link = (format_html('<a href="{}" target="_blank" rel="noopener">Open in Stripe ↗</a>',
                                obj.stripe_final_invoice_url)
                    if obj.stripe_final_invoice_url else "—")
        fin_id = (format_html(' <span style="{}">{}</span>', _ID, obj.stripe_final_invoice_id)
                  if obj.stripe_final_invoice_id else "")
        rows.append(format_html(
            '<tr><td style="{td}"><strong>Final Invoice</strong></td>'
            '<td style="{td}">{status}</td>'
            '<td style="{td}">{link}{id}</td></tr>',
            td=_TD, status=fin_status, link=fin_link, id=fin_id,
        ))

        # Payment Failed (conditional)
        if obj.payment_failed:
            failed_text = "Payment failed"
            if obj.payment_failed_at:
                failed_text += " — " + obj.payment_failed_at.strftime("%Y-%m-%d %H:%M")
            rows.append(format_html(
                '<tr><td style="{td}"><strong>Payment Failed</strong></td>'
                '<td style="{td}" colspan="2"><span style="{s}">{t}</span></td></tr>',
                td=_TD, s=_RED_BOLD, t=failed_text,
            ))

        # Quote
        if obj.stripe_quote_id:
            quote_content = format_html(
                '<span style="{}">{}</span> (finalized quotes live in Stripe Dashboard)',
                _ID, obj.stripe_quote_id,
            )
        else:
            quote_content = "No quote on file"
        rows.append(format_html(
            '<tr><td style="{td}"><strong>Quote</strong></td>'
            '<td style="{td}" colspan="2">{c}</td></tr>',
            td=_TD, c=quote_content,
        ))

        table = mark_safe(
            '<table style="border-collapse:collapse;width:100%">'
            + "".join(rows)
            + "</table>"
        )
        return table


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("job", "section", "field", "changed_by", "changed_at")
    list_filter = ("section", "changed_at")
    search_fields = ("job__invoice_number", "field")
    readonly_fields = (
        "job",
        "section",
        "field",
        "old_value",
        "new_value",
        "changed_by",
        "changed_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(TroubleRequest)
class TroubleRequestAdmin(admin.ModelAdmin):
    list_display = ("subject", "job", "status", "submitted_at")
    list_filter = ("status", "submitted_at")
    search_fields = ("subject", "body", "job__invoice_number")


@admin.register(CredentialBundle)
class CredentialBundleAdmin(admin.ModelAdmin):
    list_display = ("job", "last_revealed_at", "last_exported_at", "updated_at")
    search_fields = ("job__invoice_number",)

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser


class ChecklistStepInline(admin.TabularInline):
    model = ChecklistStep
    extra = 0
    fields = ("order", "title")
    show_change_link = True
    ordering = ("order",)


def _renumber(queryset):
    # Re-sort the queryset by (order, id) and rewrite `order` to clean
    # sequential integers 1..N. Lets the user enter a fractional value
    # (e.g. 2.5) to insert between existing rows and get integers back
    # on save.
    rows = list(queryset.order_by("order", "id"))
    for idx, row in enumerate(rows, start=1):
        if row.order != idx:
            row.order = idx
            row.save(update_fields=["order"])


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "version", "step_count", "created_at")
    list_filter = ("slug",)
    search_fields = ("title", "slug")
    ordering = ("slug", "-version")
    inlines = [ChecklistStepInline]
    readonly_fields = ("created_at",)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        _renumber(form.instance.steps)

    @admin.display(description="Steps")
    def step_count(self, obj):
        return obj.steps.count()


class ChecklistItemInline(admin.StackedInline):
    model = ChecklistItem
    extra = 0
    fields = ("order", "kind", "body_md", "capture_key", "capture_label", "capture_placeholder")
    ordering = ("order",)


@admin.register(ChecklistStep)
class ChecklistStepAdmin(admin.ModelAdmin):
    list_display = ("template", "display_order", "title", "item_count", "check_count", "capture_count")
    list_filter = ("template",)
    search_fields = ("title", "intro_md")
    ordering = ("template", "order")
    inlines = [ChecklistItemInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        _renumber(form.instance.items)

    @admin.display(description="Order", ordering="order")
    def display_order(self, obj):
        return _fmt_order(obj.order)

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()

    @admin.display(description="Checks")
    def check_count(self, obj):
        return obj.items.filter(kind="check").count()

    @admin.display(description="Captures")
    def capture_count(self, obj):
        return obj.items.filter(kind="capture").count()


@admin.register(BackendInstallItemState)
class BackendInstallItemStateAdmin(admin.ModelAdmin):
    list_display = ("backend_install", "item", "checked", "checked_by", "checked_at")
    list_filter = ("checked",)
    search_fields = ("backend_install__job__invoice_number", "notes")
    raw_id_fields = ("backend_install", "item", "checked_by")
    readonly_fields = ("checked_at",)


@admin.register(BackendInstallCapture)
class BackendInstallCaptureAdmin(admin.ModelAdmin):
    list_display = ("backend_install", "key", "value_preview", "updated_at")
    search_fields = ("backend_install__job__invoice_number", "key", "value")
    raw_id_fields = ("backend_install",)
    readonly_fields = ("updated_at",)

    @admin.display(description="Value")
    def value_preview(self, obj):
        return (obj.value[:60] + "…") if len(obj.value) > 60 else obj.value


class PackageDeviceInline(admin.TabularInline):
    model = PackageDevice
    extra = 1
    fields = ("device", "quantity")
    autocomplete_fields = ("device",)


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("name", "base_price", "device_count", "active")
    list_filter = ("active",)
    search_fields = ("name", "description")
    list_editable = ("active",)
    inlines = [PackageDeviceInline]

    @admin.display(description="Devices")
    def device_count(self, obj):
        return obj.devices.count()


@admin.register(CatalogDevice)
class CatalogDeviceAdmin(admin.ModelAdmin):
    list_display = ("device_type", "model_name", "function_slug", "supplier", "supplier_sku", "default_cost", "active")
    list_filter = ("device_type", "active", "function_slug")
    search_fields = ("model_name", "supplier", "supplier_sku", "notes", "function_slug")
    ordering = ("device_type", "model_name")
    list_editable = ("function_slug", "active")


@admin.register(InternalPrep)
class InternalPrepAdmin(admin.ModelAdmin):
    list_display = ("job", "github_username", "github_created", "picklist_picked", "updated_at")
    search_fields = ("job__invoice_number", "github_username")
    readonly_fields = ("created_at", "updated_at")


class RoomDeviceInline(admin.TabularInline):
    model = RoomDevice
    extra = 0
    fields = ("device", "quantity", "confirmed", "notes")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("job", "room_type", "custom_name", "device_count", "order")
    list_filter = ("room_type",)
    search_fields = ("job__invoice_number", "custom_name")
    inlines = [RoomDeviceInline]

    @admin.display(description="Devices")
    def device_count(self, obj):
        return obj.devices.count()


@admin.register(PreInstallItemState)
class PreInstallItemStateAdmin(admin.ModelAdmin):
    list_display = ("pre_install_checklist", "item", "checked", "checked_by", "checked_at")
    list_filter = ("checked",)
    search_fields = ("pre_install_checklist__job__invoice_number", "notes")
    raw_id_fields = ("pre_install_checklist", "item", "checked_by")
    readonly_fields = ("checked_at",)


@admin.register(PreInstallCapture)
class PreInstallCaptureAdmin(admin.ModelAdmin):
    list_display = ("pre_install_checklist", "key", "value_preview", "updated_at")
    search_fields = ("pre_install_checklist__job__invoice_number", "key", "value")
    raw_id_fields = ("pre_install_checklist",)
    readonly_fields = ("updated_at",)

    @admin.display(description="Value")
    def value_preview(self, obj):
        return (obj.value[:60] + "…") if len(obj.value) > 60 else obj.value


admin.site.site_header = "DFHA internal tools"
admin.site.site_title = "DFHA admin"
admin.site.index_title = "Jobs, customers, and installs"
