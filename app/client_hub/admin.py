from django.contrib import admin
from django.utils.html import format_html

from .models import MagicLinkToken, ServicePlanChangeRequest, WorkRequest

_STATUS_COLORS = {
    # WorkRequest
    'new': ('#b91c1c', 'New'),
    'in_review': ('#c2410c', 'In Review'),
    'contacted': ('#1d4ed8', 'Contacted'),
    'closed': ('#6b7280', 'Closed'),
    # ServicePlanChangeRequest
    'pending': ('#b91c1c', 'Pending'),
    'completed': ('#15803d', 'Completed'),
    'cancelled': ('#6b7280', 'Cancelled'),
}


def _status_badge(status_value, label):
    color, _ = _STATUS_COLORS.get(status_value, ('#6b7280', label))
    weight = 'bold' if status_value == 'new' else 'normal'
    return format_html(
        '<span style="color:{};font-weight:{}">{}</span>',
        color, weight, label,
    )


@admin.register(WorkRequest)
class WorkRequestAdmin(admin.ModelAdmin):
    list_display = ['customer', 'status_col', 'get_request_types_display', 'preferred_contact', 'created_at']
    list_filter = ['status', 'preferred_contact', 'created_at']
    search_fields = ['customer__last_name', 'customer__first_name', 'contact_email', 'description']
    ordering = ['status', '-created_at']
    readonly_fields = ['customer', 'property', 'request_types', 'service_plan_tier', 'service_since', 'created_at']

    @admin.display(description='Status')
    def status_col(self, obj):
        return _status_badge(obj.status, obj.get_status_display())


@admin.register(ServicePlanChangeRequest)
class ServicePlanChangeRequestAdmin(admin.ModelAdmin):
    list_display = ['customer', 'property', 'request_type', 'current_tier', 'requested_tier', 'status_col', 'created_at']
    list_filter = ['status', 'request_type']
    search_fields = ['customer__last_name', 'customer__first_name']
    ordering = ['status', '-created_at']
    readonly_fields = ['customer', 'property', 'request_type', 'current_tier', 'requested_tier', 'reason', 'created_at']

    @admin.display(description='Status')
    def status_col(self, obj):
        return _status_badge(obj.status, obj.get_status_display())


@admin.register(MagicLinkToken)
class MagicLinkTokenAdmin(admin.ModelAdmin):
    list_display = ['customer', 'created_at', 'expires_at', 'used_at']
    readonly_fields = ['customer', 'token', 'created_at', 'expires_at', 'used_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
