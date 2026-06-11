from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from encrypted_model_fields.fields import EncryptedCharField


class InstalledSystem(models.Model):
    class SystemType(models.TextChoices):
        LIGHTING = 'lighting', 'Lighting Control'
        HVAC = 'hvac', 'HVAC / Climate Control'
        NETWORKING = 'networking', 'Networking / WiFi Infrastructure'
        VIDEO = 'video', 'Video Systems'
        SHADES = 'shades', 'Motorized Shades / Blinds'
        ACCESS = 'access', 'Access Control'
        PRESENCE = 'presence', 'Presence Detection'
        CONTROL_INTERFACE = 'control_interface', 'Control Interface'
        OTHER = 'other', 'Other'

    customer = models.ForeignKey(
        'jobs.Customer',
        on_delete=models.PROTECT,
        related_name='installed_systems',
    )
    job = models.ForeignKey(
        'jobs.Job',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='installed_systems',
    )
    system_type = models.CharField(max_length=20, choices=SystemType.choices)
    name = models.CharField(max_length=200)
    manufacturer = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['customer', 'system_type', 'name']

    def __str__(self):
        return f"{self.customer} — {self.get_system_type_display()}: {self.name}"


class SystemCredential(models.Model):
    system = models.ForeignKey(
        InstalledSystem,
        on_delete=models.CASCADE,
        related_name='credentials',
    )
    label = models.CharField(max_length=200)
    portal_url = models.CharField(max_length=500, blank=True)
    username = models.CharField(max_length=200, blank=True)
    password = EncryptedCharField(max_length=1000, blank=True)
    api_key = EncryptedCharField(max_length=1000, blank=True)
    notes = models.TextField(blank=True)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.system} — {self.label}"


class Device(models.Model):
    system = models.ForeignKey(
        InstalledSystem,
        on_delete=models.CASCADE,
        related_name='devices',
    )
    job = models.ForeignKey(
        'jobs.Job',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client_devices',
    )
    name = models.CharField(max_length=200)
    device_type = models.CharField(max_length=100, blank=True)
    manufacturer = models.CharField(max_length=200, blank=True)
    model_number = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    mac_address = models.CharField(max_length=17, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    firmware_version = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['system', 'name']

    def __str__(self):
        return f"{self.system.customer} — {self.name}"


class DeviceCredential(models.Model):
    class CredentialType(models.TextChoices):
        PASSWORD = 'password', 'Password'
        API_KEY = 'api_key', 'API Key'
        PIN = 'pin', 'PIN'
        OTHER = 'other', 'Other'

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name='credentials',
    )
    label = models.CharField(max_length=200)
    credential_type = models.CharField(max_length=20, choices=CredentialType.choices)
    username = models.CharField(max_length=200, blank=True)
    value = EncryptedCharField(max_length=1000)
    notes = models.TextField(blank=True)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.device} — {self.label}"


class CredentialAccessLog(models.Model):
    accessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='credential_access_logs',
    )
    access_time = models.DateTimeField(auto_now_add=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    credential = GenericForeignKey('content_type', 'object_id')
    action = models.CharField(max_length=50)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-access_time']

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("CredentialAccessLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("CredentialAccessLog entries cannot be deleted.")

    def __str__(self):
        return f"{self.accessed_by} — {self.action} at {self.access_time}"


class CredentialDeletionRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        STAFF_CONTACTED = 'staff_contacted', 'Staff Contacted'
        CONFIRMED = 'confirmed', 'Confirmed'
        EXECUTED = 'executed', 'Executed'
        CANCELLED = 'cancelled', 'Cancelled'

    customer = models.ForeignKey(
        'jobs.Customer',
        on_delete=models.PROTECT,
        related_name='deletion_requests',
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    requested_by = models.CharField(max_length=300, blank=True)
    scope_notes = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    staff_assigned = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_deletion_requests',
    )
    staff_notes = models.TextField(blank=True)
    re_onboarding_fee_disclosed = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Deletion request: {self.customer} ({self.get_status_display()})"
