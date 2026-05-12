from django.conf import settings
from django.db import models


class Customer(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=40, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["last_name"])]

    def __str__(self):
        return f"{self.last_name}, {self.first_name}"


class Job(models.Model):
    class Status(models.TextChoices):
        SOLD = "sold", "Sold"
        PRE_INSTALL = "pre_install", "Pre-install"
        BACKEND = "backend", "Backend prep"
        PAIRING = "pairing", "Pairing"
        AUTOMATION = "automation", "Automation config"
        ONSITE = "onsite", "On-site install"
        WALKTHROUGH = "walkthrough", "Walkthrough"
        COMPLETE = "complete", "Complete"
        CANCELLED = "cancelled", "Cancelled"

    invoice_number = models.CharField(max_length=40, primary_key=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="jobs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SOLD)
    sold_on = models.DateField(null=True, blank=True)
    install_date = models.DateField(null=True, blank=True)
    package_summary = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-install_date", "-created_at"]
        indexes = [
            models.Index(fields=["install_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Job {self.invoice_number} — {self.customer}"

    @property
    def is_locked(self):
        return (
            hasattr(self, "walkthrough_signoff")
            and self.walkthrough_signoff.signed_at is not None
        )


class InstallRecord(models.Model):
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def is_complete(self):
        return self.completed_at is not None


class BackendInstall(InstallRecord):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="backend_install")
    progress = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"BackendInstall for {self.job_id}"


class PairingSheet(InstallRecord):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="pairing_sheet")
    devices = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"PairingSheet for {self.job_id}"


class AutomationConfig(InstallRecord):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="automation_config")
    blueprints = models.JSONField(default=list, blank=True)
    custom_yaml = models.TextField(blank=True)

    def __str__(self):
        return f"AutomationConfig for {self.job_id}"


class OnsiteInstall(InstallRecord):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="onsite_install")
    vlan_changes = models.TextField(blank=True)
    tailscale_account = models.CharField(max_length=200, blank=True)
    remote_monitoring = models.TextField(blank=True)

    def __str__(self):
        return f"OnsiteInstall for {self.job_id}"


class WalkthroughSignoff(models.Model):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="walkthrough_signoff")
    signed_at = models.DateTimeField(null=True, blank=True)
    signed_by_name = models.CharField(max_length=200, blank=True)
    signed_by_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="signoffs_witnessed",
    )
    customer_acknowledgement = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Walkthrough for {self.job_id}"


class AuditLogEntry(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="audit_entries")
    section = models.CharField(max_length=80)
    field = models.CharField(max_length=120)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_changes",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        indexes = [models.Index(fields=["job", "-changed_at"])]

    def __str__(self):
        return f"{self.job_id}.{self.section}.{self.field} @ {self.changed_at:%Y-%m-%d}"


class ServiceSubscription(models.Model):
    class Tier(models.TextChoices):
        BASIC = "basic", "Basic"
        STANDARD = "standard", "Standard"
        PREMIUM = "premium", "Premium"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELLED = "cancelled", "Cancelled"

    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="subscription")
    tier = models.CharField(max_length=20, choices=Tier.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    stripe_customer_id = models.CharField(max_length=80, blank=True)
    stripe_subscription_id = models.CharField(max_length=80, blank=True)
    started_at = models.DateField(null=True, blank=True)
    cancelled_at = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_tier_display()} for {self.job_id}"


class TroubleRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="trouble_requests")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trouble_requests",
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    submitted_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.subject} ({self.job_id})"


class CredentialBundle(models.Model):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="credentials")
    # v1 stores payload as plaintext JSON. Encryption + one-time encrypted
    # export ship in Weeks 11–12 (PLANNING.md §6). Until then, treat as
    # sensitive: admin access is gated on staff role.
    payload = models.JSONField(default=dict, blank=True)
    last_revealed_at = models.DateTimeField(null=True, blank=True)
    last_exported_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Credentials for {self.job_id}"
