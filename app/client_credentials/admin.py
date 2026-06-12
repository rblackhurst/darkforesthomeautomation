from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    CredentialAccessLog,
    CredentialDeletionRequest,
    Device,
    DeviceCredential,
    InstalledSystem,
    SystemCredential,
)


class SystemCredentialInline(admin.StackedInline):
    model = SystemCredential
    extra = 0
    fields = ['label', 'portal_url', 'username', 'notes', 'is_visible', 'view_credentials_link']
    readonly_fields = ['view_credentials_link']

    @admin.display(description='')
    def view_credentials_link(self, obj):
        if obj.pk is None:
            return 'Save to view credentials'
        url = reverse('client_credentials:system_credential_detail', args=[obj.pk])
        return format_html('<a href="{}">&#128274; View credentials &rarr;</a>', url)


class DeviceInline(admin.StackedInline):
    model = Device
    extra = 0
    show_change_link = True
    fields = [
        'name', 'device_type', 'manufacturer', 'model_number',
        'serial_number', 'mac_address', 'ip_address', 'firmware_version',
        'location', 'job', 'notes', 'is_visible', 'credential_summary_col',
    ]
    readonly_fields = ['credential_summary_col']

    @admin.display(description='Credentials')
    def credential_summary_col(self, obj):
        if obj.pk is None:
            return '—'
        count = obj.credentials.filter(is_visible=True).count()
        if count == 0:
            return 'No credentials'
        change_url = reverse('admin:client_credentials_device_change', args=[obj.pk])
        return format_html(
            '{} credential{} &mdash; <a href="{}">&#8594; View device</a>',
            count, 's' if count != 1 else '', change_url,
        )


@admin.register(InstalledSystem)
class InstalledSystemAdmin(admin.ModelAdmin):
    list_display = ['property_col', 'customer_col', 'system_type', 'name', 'is_visible', 'device_count_col', 'credential_count_col']
    list_filter = ['system_type', 'is_visible']
    search_fields = ['name', 'property__customer__last_name', 'property__customer__first_name', 'property__name']
    list_select_related = ['property__customer']
    inlines = [SystemCredentialInline, DeviceInline]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_visible=True).select_related('property__customer')

    @admin.display(description='Property', ordering='property__name')
    def property_col(self, obj):
        return obj.property.name

    @admin.display(description='Customer', ordering='property__customer__last_name')
    def customer_col(self, obj):
        return str(obj.property.customer)

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Devices')
    def device_count_col(self, obj):
        count = obj.devices.filter(is_visible=True).count()
        return f'{count} device{"s" if count != 1 else ""}' if count else 'No devices'

    @admin.display(description='Credentials')
    def credential_count_col(self, obj):
        count = obj.credentials.filter(is_visible=True).count()
        return f'{count} credential{"s" if count != 1 else ""}' if count else 'No credentials'


class DeviceCredentialInline(admin.StackedInline):
    model = DeviceCredential
    extra = 0
    fields = ['label', 'credential_type', 'username', 'notes', 'is_visible', 'view_credentials_link']
    readonly_fields = ['view_credentials_link']

    @admin.display(description='')
    def view_credentials_link(self, obj):
        if obj.pk is None:
            return 'Save to view credentials'
        url = reverse('client_credentials:device_credential_detail', args=[obj.pk])
        return format_html('<a href="{}">&#128274; View credentials &rarr;</a>', url)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['name', 'system', 'device_type', 'location', 'ip_address', 'is_visible']
    list_filter = ['is_visible', 'device_type']
    search_fields = ['name', 'system__property__customer__last_name', 'serial_number', 'mac_address']
    list_select_related = True
    inlines = [DeviceCredentialInline]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_visible=True)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SystemCredential)
class SystemCredentialAdmin(admin.ModelAdmin):
    list_display = ['system', 'label', 'is_visible']
    list_filter = ['is_visible']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_visible=True)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeviceCredential)
class DeviceCredentialAdmin(admin.ModelAdmin):
    list_display = ['device', 'label', 'credential_type', 'is_visible']
    list_filter = ['credential_type', 'is_visible']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_visible=True)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CredentialAccessLog)
class CredentialAccessLogAdmin(admin.ModelAdmin):
    list_display = ['access_time', 'accessed_by', 'action', 'content_type', 'object_id']
    ordering = ['-access_time']
    readonly_fields = ['accessed_by', 'access_time', 'content_type', 'object_id', 'action', 'notes']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Staff daily queue bookmark: /admin/client_credentials/credentialdeletionrequest/?status=pending
@admin.register(CredentialDeletionRequest)
class CredentialDeletionRequestAdmin(admin.ModelAdmin):
    list_display = [
        'customer', 'status_col', 'requested_at', 'requested_by',
        'staff_assigned', 're_onboarding_fee_disclosed',
    ]
    list_filter = ['status', 'staff_assigned', 're_onboarding_fee_disclosed']
    search_fields = ['customer__last_name', 'customer__first_name', 'requested_by', 'scope_notes']
    ordering = ['status', 'requested_at']
    fields = [
        'customer', 'requested_at', 'requested_by', 'scope_notes',
        'status', 'staff_assigned', 'staff_notes',
        're_onboarding_fee_disclosed', 'resolved_at',
    ]
    readonly_fields = ['requested_at', 'customer']

    @admin.display(description='Status')
    def status_col(self, obj):
        styles = {
            'pending': 'color:#c62828;font-weight:bold',
            'staff_contacted': 'color:#e65100',
            'confirmed': 'color:#1565c0',
            'executed': 'color:#2e7d32',
            'cancelled': 'color:#666',
        }
        labels = {
            'pending': '&#9888; Pending',
            'staff_contacted': 'Staff Contacted',
            'confirmed': 'Confirmed',
            'executed': 'Executed',
            'cancelled': 'Cancelled',
        }
        style = styles.get(obj.status, '')
        label = labels.get(obj.status, obj.get_status_display())
        return format_html('<span style="{}">{}</span>', style, label)
