from django.db import models


class RefundRecord(models.Model):
    """
    Written by issue_refund() for every staff-initiated refund.
    Also used to log any refund detected via webhook that wasn't staff-initiated.
    """
    job = models.ForeignKey(
        'jobs.Job',
        on_delete=models.CASCADE,
        related_name='refunds',
    )
    stripe_refund_id = models.CharField(max_length=255, unique=True)
    invoice_type = models.CharField(max_length=20)  # 'deposit' or 'final'
    amount_cents = models.PositiveIntegerField()
    reason = models.TextField()
    issued_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Refund {self.stripe_refund_id} — {self.job_id}"


class InternalAlert(models.Model):
    """
    Created by the webhook handler when a payment fails or a subscription goes
    past due. Surfaced in the Admin Dashboard (Phase 3) for staff review.
    """
    ALERT_TYPES = [
        ('payment_failed', 'Payment Failed'),
        ('subscription_past_due', 'Subscription Past Due'),
    ]

    job = models.ForeignKey(
        'jobs.Job',
        on_delete=models.CASCADE,
        related_name='alerts',
    )
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES)
    stripe_event_id = models.CharField(max_length=255, unique=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_alert_type_display()} — {self.job_id}"
