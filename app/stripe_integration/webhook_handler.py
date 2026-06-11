import logging

from django.utils import timezone

from jobs.models import Job
from stripe_integration.models import InternalAlert
from stripe_integration.services import PRICE_TO_TIER, create_subscription

logger = logging.getLogger(__name__)


def _to_dict(obj):
    """
    Recursively convert a Stripe SDK StripeObject (or any nested structure)
    to plain Python dicts/lists so all handlers can use .get() and [] safely.

    Stripe SDK objects returned from event['data']['object'] do not support
    .get() — they raise AttributeError instead. The exact API differs by
    how the event was constructed:
      - stripe.Webhook.construct_event() → may expose to_dict_recursive()
      - stripe.Event.construct_from()   → exposes _data but not to_dict_recursive
                                          and not .keys()
    This function handles all three cases in order.
    """
    if obj is None:
        return {}
    if hasattr(obj, 'to_dict_recursive'):
        return obj.to_dict_recursive()
    if hasattr(obj, '_data'):
        # StripeObject from construct_from(): _data is a plain dict whose
        # values may themselves be StripeObjects — recurse to flatten them.
        return _to_dict(dict(obj._data))
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    return obj


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
    invoice = _to_dict(event['data']['object'])
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
        job.save()
    elif invoice_type == 'final':
        job.final_paid = True
        job.payment_failed = False
        job.payment_failed_at = None
        job.status = Job.Status.FINAL_PAID
        job.save()

        pending_price_id = job.pending_subscription_price_id
        if pending_price_id:
            job.pending_subscription_price_id = ''
            job.save(update_fields=['pending_subscription_price_id'])
            try:
                create_subscription(job, pending_price_id)
            except Exception:
                logger.exception("invoice.paid: failed to start subscription for job %s", job.pk)


def _handle_invoice_payment_failed(event):
    invoice = _to_dict(event['data']['object'])
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
    if job.stripe_deposit_invoice_id and invoice.get('id') == job.stripe_deposit_invoice_id:
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
    subscription = _to_dict(event['data']['object'])

    sub_id = subscription.get('id')
    try:
        job = Job.objects.get(stripe_subscription_id=sub_id)
    except Job.DoesNotExist:
        logger.warning("customer.subscription.updated: subscription %s not found", sub_id)
        return

    job.subscription_status = subscription.get('status')
    new_price_id = subscription['items']['data'][0]['price']['id']
    job.plan_tier = PRICE_TO_TIER.get(new_price_id, job.plan_tier)
    job.save()


def _handle_subscription_deleted(event):
    subscription = _to_dict(event['data']['object'])

    sub_id = subscription.get('id')
    try:
        job = Job.objects.get(stripe_subscription_id=sub_id)
    except Job.DoesNotExist:
        logger.warning("customer.subscription.deleted: subscription %s not found", sub_id)
        return

    job.subscription_status = 'cancelled'
    job.save()


def _handle_charge_refunded(event):
    # Catches refunds initiated directly in the Stripe Dashboard (not via issue_refund()).
    # For staff-initiated refunds, RefundRecord is already created by issue_refund().
    # get_or_create on stripe_refund_id avoids duplicates.
    from stripe_integration.models import RefundRecord

    charge = _to_dict(event['data']['object'])

    # Attempt to resolve the job from charge metadata.
    job_id = charge.get('metadata', {}).get('dfha_job_id')
    job = None
    if job_id:
        try:
            job = Job.objects.get(pk=job_id)
        except Job.DoesNotExist:
            logger.warning("charge.refunded: Job %s not found in metadata", job_id)

    if job is None:
        logger.warning(
            "charge.refunded: could not resolve job for charge %s — skipping RefundRecord",
            charge.get('id'),
        )
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
