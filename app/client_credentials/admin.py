from django.contrib import admin

from .models import (
    CredentialAccessLog,
    CredentialDeletionRequest,
    Device,
    DeviceCredential,
    InstalledSystem,
    SystemCredential,
)


@admin.register(InstalledSystem)
class InstalledSystemAdmin(admin.ModelAdmin):
    list_display = ['customer', 'system_type', 'name', 'is_visible']
    list_filter = ['system_type', 'is_visible']


@admin.register(SystemCredential)
class SystemCredentialAdmin(admin.ModelAdmin):
    # Encrypted fields (password, api_key) excluded from list_display per spec.
    list_display = ['system', 'label', 'is_visible']
    list_filter = ['is_visible']


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['system', 'name', 'device_type', 'location', 'is_visible']
    list_filter = ['is_visible']


@admin.register(DeviceCredential)
class DeviceCredentialAdmin(admin.ModelAdmin):
    # Encrypted field (value) excluded from list_display per spec.
    list_display = ['device', 'label', 'credential_type', 'is_visible']
    list_filter = ['credential_type', 'is_visible']


@admin.register(CredentialAccessLog)
class CredentialAccessLogAdmin(admin.ModelAdmin):
    list_display = ['accessed_by', 'action', 'access_time', 'content_type', 'object_id']
    readonly_fields = ['accessed_by', 'access_time', 'content_type', 'object_id', 'action', 'notes']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CredentialDeletionRequest)
class CredentialDeletionRequestAdmin(admin.ModelAdmin):
    list_display = ['customer', 'status', 'requested_at', 'staff_assigned']
    list_filter = ['status']
