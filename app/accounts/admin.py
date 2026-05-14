from django.contrib import admin

from .models import EmployeeTOTP, RecoveryCode


@admin.register(EmployeeTOTP)
class EmployeeTOTPAdmin(admin.ModelAdmin):
    list_display = ("user", "is_confirmed", "confirmed_at", "updated_at")
    readonly_fields = ("secret", "last_used_counter", "created_at", "updated_at")
    search_fields = ("user__username", "user__email")
    actions = ["reset_enrolment"]

    @admin.action(description="Reset TOTP enrolment (forces re-setup on next login)")
    def reset_enrolment(self, request, queryset):
        from .models import _new_totp_secret
        for totp in queryset:
            totp.secret = _new_totp_secret()
            totp.confirmed_at = None
            totp.last_used_counter = 0
            totp.save()
        self.message_user(request, f"Reset {queryset.count()} TOTP enrolment(s).")


@admin.register(RecoveryCode)
class RecoveryCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "used_at", "created_at")
    readonly_fields = ("user", "code_hash", "used_at", "created_at")
    search_fields = ("user__username", "user__email")

    def has_add_permission(self, request):
        return False
