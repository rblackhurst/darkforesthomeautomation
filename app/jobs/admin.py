from django.contrib import admin

from .models import (
    AuditLogEntry,
    AutomationConfig,
    BackendInstall,
    BackendInstallCapture,
    BackendInstallItemState,
    ChecklistItem,
    ChecklistStep,
    ChecklistTemplate,
    CredentialBundle,
    Customer,
    Job,
    OnsiteInstall,
    PairingSheet,
    ServiceSubscription,
    TroubleRequest,
    WalkthroughSignoff,
    _fmt_order,
)


class BackendInstallInline(admin.StackedInline):
    model = BackendInstall
    extra = 0
    can_delete = False


class PairingSheetInline(admin.StackedInline):
    model = PairingSheet
    extra = 0
    can_delete = False


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


class ServiceSubscriptionInline(admin.StackedInline):
    model = ServiceSubscription
    extra = 0
    can_delete = False


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "email", "city", "state")
    search_fields = ("last_name", "first_name", "email", "phone")
    list_filter = ("state",)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "status", "install_date", "is_locked")
    list_filter = ("status", "install_date")
    search_fields = ("invoice_number", "customer__last_name", "customer__first_name")
    autocomplete_fields = ("customer",)
    date_hierarchy = "install_date"
    inlines = [
        BackendInstallInline,
        PairingSheetInline,
        AutomationConfigInline,
        OnsiteInstallInline,
        WalkthroughSignoffInline,
        ServiceSubscriptionInline,
    ]


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


admin.site.site_header = "DFHA internal tools"
admin.site.site_title = "DFHA admin"
admin.site.index_title = "Jobs, customers, and installs"
