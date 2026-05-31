import logging

from django.utils import timezone

from jobs.models import Job
from stripe_integration.models import InternalAlert
from stripe_integration.services import PRICE_TO_TIER

logger = logging.getLogger(__name__)


def handle_stripe_event(event):
    """Route inbound Stripe events. Unrecognized types are silently ignored."""
    event_type = event['type']

    handlers = {
        'invoice.paid': _handle_invoice_paid,
        'invoice.payment_failed': _handle_invoice_payment_failed,
        'customer.subscription.updated': _handle_subscription_updated,
        'customer.subscription.deleted': _handle_subscription_deleted,
        'charge.refunded': _handle_charge_refunded,
    }

    handler = handlers.get(event_type)
    if handler:
        handler(event)


def _handle_invoice_paid(event):
    invoice = event['data']['object']
    job_id = invoice.get('metadata', {}).get('dfha_job_id')
    invoice_type = invoice.get('metadata', {}).get('invoice_type')

    if not job_id:
        return

    try:
        job = Job.objects.get(pk=job_id)
    except Job.DoesNotExist:
        logger.warning("invoice.paid: Job %s not found", job_id)
        return

    if invoice_type == 'deposit':
        job.deposit_paid = True
        job.payment_failed = False
        job.payment_failed_at = None
        job.status = Job.Status.DEPOSIT_RECEIVED
    elif invoice_type == 'final':
        job.final_paid = True
        job.payment_failed = False
        job.payment_failed_at = None
        job.status = Job.Status.FINAL_PAID

    job.save()


def _handle_invoice_payment_failed(event):
    invoice = event['data']['object']
    job_id = invoice.get('metadata', {}).get('dfha_job_id')

    if not job_id:
        return

    try:
        job = Job.objects.get(pk=job_id)
    except Job.DoesNotExist:
        logger.warning("invoice.payment_failed: Job %s not found", job_id)
        return

    job.payment_failed = True
    job.payment_failed_at = timezone.now()
    job.save()

    # Determine which invoice failed for the alert message.
    if job.stripe_deposit_invoice_id and invoice['id'] == job.stripe_deposit_invoice_id:
        invoice_label = 'deposit'
    else:
        invoice_label = 'final'

    # get_or_create deduplicates on stripe_event_id to handle Stripe retries.
    InternalAlert.objects.get_or_create(
        stripe_event_id=event['id'],
        defaults={
            'job': job,
            'alert_type': 'payment_failed',
            'message': f"Payment failed for {invoice_label} invoice on job {job.pk}.",
        },
    )


def _handle_subscription_updated(event):
    subscription = event['data']['object']

    try:
        job = Job.objects.get(stripe_subscription_id=subscription['id'])
    except Job.DoesNotExist:
        logger.warning("customer.subscription.updated: subscription %s not found", subscription['id'])
        return

    job.subscription_status = subscription['status']
    new_price_id = subscription['items']['data'][0]['price']['id']
    job.plan_tier = PRICE_TO_TIER.get(new_price_id, job.plan_tier)
    job.save()


def _handle_subscription_deleted(event):
    subscription = event['data']['object']

    try:
        job = Job.objects.get(stripe_subscription_id=subscription['id'])
    except Job.DoesNotExist:
        logger.warning("customer.subscription.deleted: subscription %s not found", subscription['id'])
        return

    job.subscription_status = 'cancelled'
    job.save()


def _handle_charge_refunded(event):
    # Catches refunds initiated directly in the Stripe Dashboard (not via issue_refund()).
    # For staff-initiated refunds, RefundRecord is already created by issue_refund().
    # get_or_create on stripe_refund_id avoids duplicates.
    from stripe_integration.models import RefundRecord

    charge = event['data']['object']

    # Attempt to resolve the job from charge metadata.
    job_id = charge.get('metadata', {}).get('dfha_job_id')
    job = None
    if job_id:
        try:
            job = Job.objects.get(pk=job_id)
        except Job.DoesNotExist:
            logger.warning("charge.refunded: Job %s not found in metadata", job_id)

    if job is None:
        logger.warning("charge.refunded: could not resolve job for charge %s — skipping RefundRecord", charge.get('id'))
        return

    for refund in charge.get('refunds', {}).get('data', []):
        RefundRecord.objects.get_or_create(
            stripe_refund_id=refund['id'],
            defaults={
                'job': job,
                'invoice_type': 'unknown',
                'amount_cents': refund['amount'],
                'reason': refund.get('reason') or 'initiated via stripe dashboard',
                'issued_by': None,
            },
        )
