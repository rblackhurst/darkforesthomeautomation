import math
import os
import time
from calendar import monthrange
from datetime import datetime, timezone as dt_timezone

import stripe

from django.db import transaction

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# SECURITY CONSTRAINTS — DO NOT VIOLATE:
# 1. All Stripe API calls are server-side only. The browser never receives secret keys.
# 2. API keys are loaded exclusively from environment variables. Never hardcoded.
#    Never written to settings.py directly. Always os.environ.get().
# 3. Webhook endpoint validates Stripe-Signature header via stripe.Webhook.construct_event()
#    before processing any event payload. Return HTTP 400 on validation failure.
# 4. Payment UI is never built in this codebase. Customers interact with Stripe via
#    hosted_invoice_url and Stripe Billing Portal sessions only.
# 5. Future phases: Client Hub queries will always filter by authenticated user's customer
#    record. No raw ID lookups that bypass ownership checks.

# Map every known Price ID to its tier label.
# Used for plan_tier derivation and price_id validation throughout this module.
PRICE_TO_TIER = {
    k: v for k, v in {
        os.environ.get('STRIPE_PRICE_TIER1_MONTHLY'): 'tier1',
        os.environ.get('STRIPE_PRICE_TIER1_ANNUAL'):  'tier1',
        os.environ.get('STRIPE_PRICE_TIER2_MONTHLY'): 'tier2',
        os.environ.get('STRIPE_PRICE_TIER2_ANNUAL'):  'tier2',
        os.environ.get('STRIPE_PRICE_TIER3_MONTHLY'): 'tier3',
        os.environ.get('STRIPE_PRICE_TIER3_ANNUAL'):  'tier3',
    }.items() if k is not None
}

# Used to determine upgrade vs. downgrade direction in change_subscription_plan().
TIER_ORDER = {'tier1': 1, 'tier2': 2, 'tier3': 3}


# ── 7.1 Customer Management ───────────────────────────────────────────────────

def get_or_create_stripe_customer(customer) -> stripe.Customer:
    """Ensure a Stripe Customer exists for the given Django Customer. Idempotent."""
    if customer.stripe_customer_id:
        return stripe.Customer.retrieve(customer.stripe_customer_id)

    # Select-for-update to prevent duplicate creation under concurrent requests.
    with transaction.atomic():
        from jobs.models import Customer as CustomerModel
        locked = CustomerModel.objects.select_for_update().get(pk=customer.pk)
        if locked.stripe_customer_id:
            # Another request created it while we were waiting for the lock.
            customer.stripe_customer_id = locked.stripe_customer_id
            return stripe.Customer.retrieve(locked.stripe_customer_id)

        create_kwargs = {
            'name': f"{locked.first_name} {locked.last_name}".strip(),
            'email': locked.email,
            'metadata': {
                'dfha_customer_id': str(locked.pk),
                'source': 'dark_forest_ha',
            },
        }
        if locked.phone:
            create_kwargs['phone'] = locked.phone

        stripe_customer = stripe.Customer.create(**create_kwargs)
        locked.stripe_customer_id = stripe_customer.id
        locked.save()
        customer.stripe_customer_id = stripe_customer.id
        return stripe_customer


# ── 7.2 Quotes ───────────────────────────────────────────────────────────────

def create_installation_quote(job, line_items: list) -> stripe.Quote:
    """Create a Stripe Quote for all installation line items on a job."""
    get_or_create_stripe_customer(job.customer)

    quote = stripe.Quote.create(
        customer=job.customer.stripe_customer_id,
        line_items=line_items,
        expires_at=int(time.time()) + 30 * 86400,
        metadata={'dfha_job_id': str(job.pk)},
    )
    job.stripe_quote_id = quote.id
    job.save()
    return quote


def send_quote(quote_id: str) -> stripe.Quote:
    """Finalize and send the quote PDF to the customer's email."""
    return stripe.Quote.finalize_quote(quote_id)


def void_quote(quote_id: str) -> stripe.Quote:
    """Cancel a quote that will not proceed. Does not clear job.stripe_quote_id."""
    return stripe.Quote.cancel(quote_id)


# ── 7.3 Invoices ─────────────────────────────────────────────────────────────

def _stamp_pi_metadata(invoice_id: str, job_pk: str) -> None:
    """Stamp dfha_job_id on the PaymentIntent(s) for an invoice.

    Stripe API >= 2025-03-31 ("basil") removed the payment_intent field from
    Invoice; use InvoicePayment.list() to get the associated PaymentIntent IDs.
    This stamp ensures charge.refunded webhooks can resolve the job — charges
    inherit metadata from their PaymentIntent, not from the Invoice.
    """
    invoice_payments = stripe.InvoicePayment.list(invoice=invoice_id)
    for ip in invoice_payments.data:
        pi_id = ip.payment.payment_intent if ip.payment else None
        if pi_id:
            stripe.PaymentIntent.modify(
                pi_id,
                metadata={'dfha_job_id': job_pk},
            )

def create_deposit_invoice(job) -> stripe.Invoice:
    """Create Invoice #1 for 50% of the accepted quote total."""
    if not job.stripe_quote_id:
        raise ValueError("Job has no associated quote")

    quote = stripe.Quote.retrieve(job.stripe_quote_id)
    quote_total_cents = quote.amount_total

    # Always round UP to the nearest cent so the deposit is >= 50%.
    # On odd totals (e.g. $9.99 = 999 cents), deposit = ceil(499.5) = 500 cents.
    # The final invoice will be 999 - 500 = 499 cents.
    # Deposit + Final always equals quote_total_cents exactly.
    deposit_cents = math.ceil(quote_total_cents / 2)

    invoice = stripe.Invoice.create(
        customer=job.customer.stripe_customer_id,
        collection_method='send_invoice',
        days_until_due=7,
        metadata={'dfha_job_id': str(job.pk), 'invoice_type': 'deposit'},
    )
    stripe.InvoiceItem.create(
        customer=job.customer.stripe_customer_id,
        invoice=invoice.id,
        amount=deposit_cents,
        currency='usd',
        description='Installation Deposit (50%)',
    )
    finalized = stripe.Invoice.finalize_invoice(invoice.id)
    _stamp_pi_metadata(finalized.id, str(job.pk))

    job.stripe_deposit_invoice_id = finalized.id
    job.stripe_deposit_invoice_url = finalized.hosted_invoice_url
    job.save()
    return finalized


def send_deposit_invoice(job) -> str:
    """Send Invoice #1 to the customer and return the payment URL."""
    if not job.stripe_deposit_invoice_id:
        raise ValueError("No deposit invoice on this job")
    stripe.Invoice.send_invoice(job.stripe_deposit_invoice_id)
    return job.stripe_deposit_invoice_url


def create_and_send_deposit_invoice(job, total_cents: int, dfha_invoice_number: str = None) -> stripe.Invoice:
    """Create a deposit invoice from a sale total and send it entirely through Stripe.

    Stripe emails the customer directly with a hosted invoice page and payment link.
    No quote is required — the total is supplied by the caller (e.g. from sale lines).
    """
    get_or_create_stripe_customer(job.customer)
    deposit_cents = math.ceil(total_cents / 2)

    metadata = {'dfha_job_id': str(job.pk), 'invoice_type': 'deposit'}
    if dfha_invoice_number:
        metadata['dfha_invoice_number'] = dfha_invoice_number

    invoice = stripe.Invoice.create(
        customer=job.customer.stripe_customer_id,
        collection_method='send_invoice',
        days_until_due=7,
        description=(
            f"Installation Deposit — Invoice {dfha_invoice_number}"
            if dfha_invoice_number else "Installation Deposit"
        ),
        metadata=metadata,
    )
    stripe.InvoiceItem.create(
        customer=job.customer.stripe_customer_id,
        invoice=invoice.id,
        amount=deposit_cents,
        currency='usd',
        description='Installation Deposit (50%)',
    )
    finalized = stripe.Invoice.finalize_invoice(invoice.id)
    _stamp_pi_metadata(finalized.id, str(job.pk))

    job.stripe_deposit_invoice_id = finalized.id
    job.stripe_deposit_invoice_url = finalized.hosted_invoice_url
    job.save()

    stripe.Invoice.send_invoice(finalized.id)
    return finalized


def create_and_send_final_invoice(job, total_cents: int, additional_price_ids: list = None) -> stripe.Invoice:
    """Create the final invoice (remaining 50% balance + optional extras) and send via Stripe.

    Does not require a pre-existing Stripe Quote — total_cents is the original
    installation total supplied by the caller. additional_price_ids is a list
    of Stripe Price IDs to attach as extra InvoiceItems (e.g. a service plan).
    """
    if job.stripe_final_invoice_id:
        raise ValueError("Final invoice already exists for this job")

    get_or_create_stripe_customer(job.customer)

    deposit_cents = math.ceil(total_cents / 2)
    remaining_cents = total_cents - deposit_cents

    metadata = {'dfha_job_id': str(job.pk), 'invoice_type': 'final'}
    if job.display_invoice_number:
        metadata['dfha_invoice_number'] = job.display_invoice_number

    invoice = stripe.Invoice.create(
        customer=job.customer.stripe_customer_id,
        collection_method='send_invoice',
        days_until_due=7,
        description=(
            f"Installation Balance — Invoice {job.display_invoice_number}"
            if job.display_invoice_number else "Installation Balance"
        ),
        metadata=metadata,
    )
    stripe.InvoiceItem.create(
        customer=job.customer.stripe_customer_id,
        invoice=invoice.id,
        amount=remaining_cents,
        currency='usd',
        description='Installation Balance (50%)',
    )
    if additional_price_ids:
        for price_id in additional_price_ids:
            stripe.InvoiceItem.create(
                customer=job.customer.stripe_customer_id,
                invoice=invoice.id,
                pricing={'price': price_id},
            )

    finalized = stripe.Invoice.finalize_invoice(invoice.id)
    _stamp_pi_metadata(finalized.id, str(job.pk))

    job.stripe_final_invoice_id = finalized.id
    job.stripe_final_invoice_url = finalized.hosted_invoice_url
    job.save()

    stripe.Invoice.send_invoice(finalized.id)
    return finalized


def create_final_invoice(job, additional_line_items: list = None) -> stripe.Invoice:
    """Create Invoice #2 for the remaining balance plus any additions."""
    if not job.stripe_quote_id:
        raise ValueError("Job has no associated quote")
    if job.stripe_final_invoice_id:
        raise ValueError("Final invoice already exists for this job")

    quote = stripe.Quote.retrieve(job.stripe_quote_id)
    quote_total_cents = quote.amount_total

    # Same rounding formula as deposit — must be consistent.
    # Deposit + Final == quote_total_cents always.
    deposit_cents = math.ceil(quote_total_cents / 2)
    remaining_cents = quote_total_cents - deposit_cents

    invoice = stripe.Invoice.create(
        customer=job.customer.stripe_customer_id,
        collection_method='send_invoice',
        days_until_due=7,
        metadata={'dfha_job_id': str(job.pk), 'invoice_type': 'final'},
    )
    stripe.InvoiceItem.create(
        customer=job.customer.stripe_customer_id,
        invoice=invoice.id,
        amount=remaining_cents,
        currency='usd',
        description='Installation Balance',
    )
    if additional_line_items:
        for item in additional_line_items:
            stripe.InvoiceItem.create(
                customer=job.customer.stripe_customer_id,
                invoice=invoice.id,
                amount=item['price_data']['unit_amount'],
                currency='usd',
                description=item['price_data']['product_data']['name'],
            )

    finalized = stripe.Invoice.finalize_invoice(invoice.id)
    _stamp_pi_metadata(finalized.id, str(job.pk))

    job.stripe_final_invoice_id = finalized.id
    job.stripe_final_invoice_url = finalized.hosted_invoice_url
    job.save()
    return finalized


def send_final_invoice(job) -> str:
    """Send Invoice #2 to the customer and return the payment URL."""
    if not job.stripe_final_invoice_id:
        raise ValueError("No final invoice on this job")
    stripe.Invoice.send_invoice(job.stripe_final_invoice_id)
    return job.stripe_final_invoice_url


def void_invoice(invoice_id: str) -> stripe.Invoice:
    """Void an invoice before it is paid. Does not modify any Job fields."""
    return stripe.Invoice.void_invoice(invoice_id)


# ── 7.4 Subscriptions ────────────────────────────────────────────────────────

def _first_of_next_month_timestamp() -> int:
    """Return a Unix timestamp for midnight UTC on the 1st of next month."""
    now = datetime.now(dt_timezone.utc)
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=dt_timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=dt_timezone.utc)
    return int(next_month.timestamp())


def create_subscription(job, price_id: str) -> stripe.Subscription:
    """Start a service plan subscription after the final invoice is paid."""
    if not job.final_paid:
        raise ValueError("Cannot start subscription before final invoice is paid")
    if price_id not in PRICE_TO_TIER:
        raise ValueError(f"Invalid price_id: {price_id}")

    subscription = stripe.Subscription.create(
        customer=job.customer.stripe_customer_id,
        items=[{'price': price_id}],
        billing_cycle_anchor=_first_of_next_month_timestamp(),
        proration_behavior='none',
        metadata={'dfha_job_id': str(job.pk)},
    )
    job.stripe_subscription_id = subscription.id
    job.plan_tier = PRICE_TO_TIER[price_id]
    job.subscription_status = subscription.status
    job.save()
    return subscription


def change_subscription_plan(job, new_price_id: str) -> stripe.Subscription:
    """Admin-initiated plan change. Upgrades apply immediately; downgrades at period end."""
    if new_price_id not in PRICE_TO_TIER:
        raise ValueError(f"Invalid price_id: {new_price_id}")

    subscription = stripe.Subscription.retrieve(job.stripe_subscription_id)
    item_id = subscription.items.data[0].id
    current_price_id = subscription.items.data[0].price.id

    current_tier = PRICE_TO_TIER.get(current_price_id)
    new_tier = PRICE_TO_TIER[new_price_id]
    is_upgrade = TIER_ORDER[new_tier] > TIER_ORDER.get(current_tier, 0)

    if is_upgrade:
        updated = stripe.Subscription.modify(
            job.stripe_subscription_id,
            items=[{'id': item_id, 'price': new_price_id}],
            proration_behavior='create_prorations',
        )
    else:
        # Downgrade or same-tier interval change: takes effect at next billing cycle.
        updated = stripe.Subscription.modify(
            job.stripe_subscription_id,
            items=[{'id': item_id, 'price': new_price_id}],
            proration_behavior='none',
            billing_cycle_anchor='unchanged',
        )

    job.plan_tier = new_tier
    job.subscription_status = updated.status
    job.save()
    return updated


def cancel_subscription(job, immediate: bool = False) -> stripe.Subscription:
    """Cancel a customer's service plan."""
    if immediate:
        subscription = stripe.Subscription.cancel(job.stripe_subscription_id)
    else:
        subscription = stripe.Subscription.modify(
            job.stripe_subscription_id,
            cancel_at_period_end=True,
        )
    job.subscription_status = subscription.status
    job.save()
    return subscription


def get_subscription_status(job) -> dict:
    """Return current subscription state from Stripe (source of truth, not the DB)."""
    if not job.stripe_subscription_id:
        raise ValueError("No subscription on this job")
    subscription = stripe.Subscription.retrieve(job.stripe_subscription_id)
    return {
        'status': subscription.status,
        'plan_tier': PRICE_TO_TIER.get(subscription.items.data[0].price.id),
        'current_period_end': subscription.current_period_end,
        'cancel_at_period_end': subscription.cancel_at_period_end,
    }


# ── 7.5 Refunds ───────────────────────────────────────────────────────────────

def issue_refund(job, invoice_type: str, amount_cents: int, reason: str, issued_by) -> stripe.Refund:
    """Issue a partial or full refund against a deposit or final invoice payment."""
    if not reason:
        raise ValueError("reason is required")
    if amount_cents <= 0:
        raise ValueError("amount_cents must be greater than zero")
    if invoice_type not in ('deposit', 'final'):
        raise ValueError("invoice_type must be 'deposit' or 'final'")

    if invoice_type == 'deposit':
        invoice_id = job.stripe_deposit_invoice_id
    else:
        invoice_id = job.stripe_final_invoice_id

    if not invoice_id:
        raise ValueError(f"No {invoice_type} invoice found on this job")

    invoice = stripe.Invoice.retrieve(invoice_id)
    refund = stripe.Refund.create(
        payment_intent=invoice.payment_intent,
        amount=amount_cents,
        reason='requested_by_customer',
    )

    from stripe_integration.models import RefundRecord
    RefundRecord.objects.create(
        job=job,
        stripe_refund_id=refund.id,
        invoice_type=invoice_type,
        amount_cents=amount_cents,
        reason=reason,
        issued_by=issued_by,
    )
    return refund


# ── 7.6 Client Hub Support ───────────────────────────────────────────────────

def create_billing_portal_session(customer, return_url: str) -> str:
    """Generate a one-time Stripe Billing Portal URL. Do not store or cache it."""
    if not customer.stripe_customer_id:
        raise ValueError("Customer has no Stripe account")
    session = stripe.billing_portal.Session.create(
        customer=customer.stripe_customer_id,
        return_url=return_url,
    )
    return session.url


# ── 7.7 Payment State Recovery ────────────────────────────────────────────────

def sync_payment_status(job) -> dict:
    """Poll Stripe invoice state and update job payment flags.

    Use when a webhook was missed — e.g. during local dev without the stripe
    CLI running, or after a webhook outage. Only advances state forward; never
    reverts a flag that is already True. Returns a dict of fields that changed.
    """
    from jobs.models import Job as JobModel

    changed = {}

    if job.stripe_deposit_invoice_id and not job.deposit_paid:
        inv = stripe.Invoice.retrieve(job.stripe_deposit_invoice_id)
        if inv.status == 'paid':
            job.deposit_paid = True
            job.payment_failed = False
            job.payment_failed_at = None
            job.status = JobModel.Status.DEPOSIT_RECEIVED
            changed['deposit_paid'] = True

    if job.stripe_final_invoice_id and not job.final_paid:
        inv = stripe.Invoice.retrieve(job.stripe_final_invoice_id)
        if inv.status == 'paid':
            job.final_paid = True
            job.payment_failed = False
            job.payment_failed_at = None
            job.status = JobModel.Status.FINAL_PAID
            changed['final_paid'] = True

    if changed:
        job.save()

    return changed
