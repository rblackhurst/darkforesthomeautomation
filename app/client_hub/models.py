from django.db import models


class MagicLinkToken(models.Model):
    customer = models.ForeignKey(
        'jobs.Customer',
        on_delete=models.CASCADE,
        related_name='magic_link_tokens',
    )
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_valid(self):
        from django.utils import timezone
        return self.used_at is None and timezone.now() < self.expires_at

    def __str__(self):
        return f"Token for {self.customer} — expires {self.expires_at}"


class WorkRequest(models.Model):
    class RequestType(models.TextChoices):
        NEW_INSTALL = 'new_install', 'New Installation'
        NEW_AUTOMATION = 'new_automation', 'New Automation with Existing Devices'
        UPDATE_AUTOMATION = 'update_automation', 'Update Existing Automation'

    class Status(models.TextChoices):
        NEW = 'new', 'New'
        IN_REVIEW = 'in_review', 'In Review'
        CONTACTED = 'contacted', 'Contacted'
        CLOSED = 'closed', 'Closed'

    customer = models.ForeignKey(
        'jobs.Customer',
        on_delete=models.PROTECT,
        related_name='work_requests',
    )
    property = models.ForeignKey(
        'jobs.Property',
        on_delete=models.PROTECT,
        related_name='work_requests',
        null=True,
        blank=True,
    )
    # Comma-separated RequestType values
    request_types = models.CharField(max_length=200)
    description = models.TextField()
    contact_name = models.CharField(max_length=200)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=40, blank=True)
    preferred_contact = models.CharField(
        max_length=10,
        choices=[('email', 'Email'), ('phone', 'Phone')],
        default='email',
    )
    service_plan_tier = models.CharField(max_length=10, blank=True)
    service_since = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    staff_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_request_types_display(self):
        type_map = dict(self.RequestType.choices)
        return ', '.join(
            type_map.get(t.strip(), t.strip())
            for t in self.request_types.split(',')
            if t.strip()
        )

    def __str__(self):
        return f"Work request: {self.customer} ({self.created_at.date()})"


class ServicePlanChangeRequest(models.Model):
    class RequestType(models.TextChoices):
        UPGRADE = 'upgrade', 'Upgrade Plan'
        DOWNGRADE = 'downgrade', 'Downgrade Plan'
        CANCEL = 'cancel', 'Cancel Service'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONTACTED = 'contacted', 'Staff Contacted'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    customer = models.ForeignKey(
        'jobs.Customer',
        on_delete=models.PROTECT,
        related_name='plan_change_requests',
    )
    property = models.ForeignKey(
        'jobs.Property',
        on_delete=models.PROTECT,
        related_name='plan_change_requests',
    )
    request_type = models.CharField(max_length=20, choices=RequestType.choices)
    current_tier = models.CharField(max_length=10, blank=True)
    requested_tier = models.CharField(max_length=10, blank=True)
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    staff_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_request_type_display()}: {self.customer} ({self.created_at.date()})"
