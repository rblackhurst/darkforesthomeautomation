import json
from unittest.mock import patch
from django.test import TestCase

import stripe

from jobs.models import Customer, Job
from stripe_integration.models import InternalAlert


# ---------------------------------------------------------------------------
# Event factory
#
# Uses stripe.Event.construct_from() — the same construction path used in
# production when stripe.Webhook.construct_event() parses an inbound payload.
# This exercises the real StripeObject structure (nested _data, no .get(),
# no to_dict_recursive) so _to_dict() is validated against the actual SDK.
# ---------------------------------------------------------------------------

def _make_event(event_type, data_object_dict, event_id='evt_test'):
    """
    Build a stripe.Event using construct_from(), wrapping data_object_dict
    in the minimal envelope the SDK expects. The resulting event['data']['object']
    is a real StripeObject, not a plain dict.
    """
    return stripe.Event.construct_from(
        {
            'id': event_id,
            'object': 'event',
            'type': event_type,
            'data': {'object': data_object_dict},
        },
        key=None,
    )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def make_customer(**kwargs):
    defaults = dict(first_name='Jane', last_name='Smith', email='jane@example.com')
    defaults.update(kwargs)
    return Customer.objects.create(**defaults)


def make_job(customer, **kwargs):
    defaults = dict(invoice_number='TEST-001')
    defaults.update(kwargs)
    return Job.objects.create(customer=customer, **defaults)


# ---------------------------------------------------------------------------
# Webhook signature validation
# (construct_event is mocked here so the view never calls _to_dict — these
#  tests cover HTTP-layer concerns only)
# ---------------------------------------------------------------------------

class WebhookSignatureTests(TestCase):
    @patch('stripe_integration.views.stripe.Webhook.construct_event')
    def test_valid_signature_returns_200(self, mock_construct):
        mock_construct.return_value = _make_event('unknown.event', {})
        response = self.client.post(
            '/webhooks/stripe/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='valid',
        )
        self.assertEqual(response.status_code, 200)

    @patch('stripe_integration.views.stripe.Webhook.construct_event')
    def test_invalid_signature_returns_400(self, mock_construct):
        mock_construct.side_effect = stripe.error.SignatureVerificationError('bad sig', 'sig')
        response = self.client.post(
            '/webhooks/stripe/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='bad',
        )
        self.assertEqual(response.status_code, 400)

    @patch('stripe_integration.views.stripe.Webhook.construct_event')
    def test_missing_signature_returns_400(self, mock_construct):
        mock_construct.side_effect = stripe.error.SignatureVerificationError('no sig', '')
        response = self.client.post(
            '/webhooks/stripe/',
            data=b'{}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    @patch('stripe_integration.views.stripe.Webhook.construct_event')
    def test_malformed_payload_returns_400(self, mock_construct):
        mock_construct.side_effect = ValueError("invalid json")
        response = self.client.post(
            '/webhooks/stripe/',
            data=b'not-json',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='sig',
        )
        self.assertEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# invoice.paid — deposit
# ---------------------------------------------------------------------------

class InvoicePaidDepositTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.job = make_job(self.customer, stripe_deposit_invoice_id='in_dep')

    def _handle(self, data_dict):
        from stripe_integration.webhook_handler import _handle_invoice_paid
        _handle_invoice_paid(_make_event('invoice.paid', data_dict))

    def test_sets_deposit_paid(self):
        self._handle({'id': 'in_dep', 'metadata': {'dfha_job_id': 'TEST-001', 'invoice_type': 'deposit'}})
        self.job.refresh_from_db()
        self.assertTrue(self.job.deposit_paid)

    def test_clears_payment_failed(self):
        self.job.payment_failed = True
        self.job.save()
        self._handle({'id': 'in_dep', 'metadata': {'dfha_job_id': 'TEST-001', 'invoice_type': 'deposit'}})
        self.job.refresh_from_db()
        self.assertFalse(self.job.payment_failed)

    def test_advances_status_to_deposit_received(self):
        self._handle({'id': 'in_dep', 'metadata': {'dfha_job_id': 'TEST-001', 'invoice_type': 'deposit'}})
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.DEPOSIT_RECEIVED)

    def test_missing_job_id_returns_silently(self):
        self._handle({'id': 'in_x', 'metadata': {}})

    def test_nonexistent_job_id_returns_silently(self):
        self._handle({'id': 'in_x', 'metadata': {'dfha_job_id': 'NOPE-999', 'invoice_type': 'deposit'}})


# ---------------------------------------------------------------------------
# invoice.paid — final
# ---------------------------------------------------------------------------

class InvoicePaidFinalTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.job = make_job(self.customer, stripe_final_invoice_id='in_fin')

    def _handle(self, data_dict):
        from stripe_integration.webhook_handler import _handle_invoice_paid
        _handle_invoice_paid(_make_event('invoice.paid', data_dict))

    def test_sets_final_paid(self):
        self._handle({'id': 'in_fin', 'metadata': {'dfha_job_id': 'TEST-001', 'invoice_type': 'final'}})
        self.job.refresh_from_db()
        self.assertTrue(self.job.final_paid)

    def test_clears_payment_failed(self):
        self.job.payment_failed = True
        self.job.save()
        self._handle({'id': 'in_fin', 'metadata': {'dfha_job_id': 'TEST-001', 'invoice_type': 'final'}})
        self.job.refresh_from_db()
        self.assertFalse(self.job.payment_failed)

    def test_advances_status_to_final_paid(self):
        self._handle({'id': 'in_fin', 'metadata': {'dfha_job_id': 'TEST-001', 'invoice_type': 'final'}})
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.FINAL_PAID)

    @patch('stripe_integration.webhook_handler.create_subscription')
    def test_starts_subscription_when_pending_price_id_set(self, mock_create_sub):
        self.job.pending_subscription_price_id = 'price_tier3_annual'
        self.job.final_paid = True
        self.job.save()

        self._handle({'id': 'in_fin', 'metadata': {'dfha_job_id': 'TEST-001', 'invoice_type': 'final'}})

        mock_create_sub.assert_called_once_with(self.job, 'price_tier3_annual')
        self.job.refresh_from_db()
        self.assertEqual(self.job.pending_subscription_price_id, '')

    @patch('stripe_integration.webhook_handler.create_subscription')
    def test_no_subscription_when_no_pending_price_id(self, mock_create_sub):
        self._handle({'id': 'in_fin', 'metadata': {'dfha_job_id': 'TEST-001', 'invoice_type': 'final'}})
        mock_create_sub.assert_not_called()


# ---------------------------------------------------------------------------
# invoice.payment_failed
# ---------------------------------------------------------------------------

class InvoicePaymentFailedTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.job = make_job(self.customer, stripe_deposit_invoice_id='in_dep')

    def _handle(self, data_dict, event_id='evt_1'):
        from stripe_integration.webhook_handler import _handle_invoice_payment_failed
        _handle_invoice_payment_failed(_make_event('invoice.payment_failed', data_dict, event_id=event_id))

    def test_sets_payment_failed(self):
        self._handle({'id': 'in_dep', 'metadata': {'dfha_job_id': 'TEST-001'}})
        self.job.refresh_from_db()
        self.assertTrue(self.job.payment_failed)

    def test_sets_payment_failed_at(self):
        self._handle({'id': 'in_dep', 'metadata': {'dfha_job_id': 'TEST-001'}})
        self.job.refresh_from_db()
        self.assertIsNotNone(self.job.payment_failed_at)

    def test_creates_internal_alert(self):
        self._handle({'id': 'in_dep', 'metadata': {'dfha_job_id': 'TEST-001'}}, event_id='evt_fail1')
        self.assertEqual(InternalAlert.objects.filter(stripe_event_id='evt_fail1').count(), 1)

    def test_duplicate_event_creates_only_one_alert(self):
        self._handle({'id': 'in_dep', 'metadata': {'dfha_job_id': 'TEST-001'}}, event_id='evt_dup')
        self._handle({'id': 'in_dep', 'metadata': {'dfha_job_id': 'TEST-001'}}, event_id='evt_dup')
        self.assertEqual(InternalAlert.objects.filter(stripe_event_id='evt_dup').count(), 1)


# ---------------------------------------------------------------------------
# customer.subscription.updated
# ---------------------------------------------------------------------------

class SubscriptionUpdatedTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.job = make_job(self.customer, stripe_subscription_id='sub_abc')

    def _handle(self, data_dict):
        from stripe_integration.webhook_handler import _handle_subscription_updated
        _handle_subscription_updated(_make_event('customer.subscription.updated', data_dict))

    def test_updates_subscription_status(self):
        with patch('stripe_integration.webhook_handler.PRICE_TO_TIER', {'price_t1': 'tier1'}):
            self._handle({
                'id': 'sub_abc', 'status': 'past_due',
                'items': {'data': [{'price': {'id': 'price_t1'}}]},
            })
        self.job.refresh_from_db()
        self.assertEqual(self.job.subscription_status, 'past_due')

    def test_updates_service_plan_tier(self):
        with patch('stripe_integration.webhook_handler.PRICE_TO_TIER', {'price_t2': 'tier2'}):
            self._handle({
                'id': 'sub_abc', 'status': 'active',
                'items': {'data': [{'price': {'id': 'price_t2'}}]},
            })
        self.job.refresh_from_db()
        self.assertEqual(self.job.service_plan_tier, 'tier2')

    def test_monthly_price_sets_billing_interval_monthly(self):
        with patch('stripe_integration.webhook_handler.PRICE_TO_TIER', {'price_t1_mo': 'tier1'}):
            self._handle({
                'id': 'sub_abc', 'status': 'active',
                'items': {'data': [{'price': {'id': 'price_t1_mo', 'recurring': {'interval': 'month'}}}]},
            })
        self.job.refresh_from_db()
        self.assertEqual(self.job.billing_interval, 'monthly')

    def test_annual_price_sets_billing_interval_annual(self):
        with patch('stripe_integration.webhook_handler.PRICE_TO_TIER', {'price_t1_yr': 'tier1'}):
            self._handle({
                'id': 'sub_abc', 'status': 'active',
                'items': {'data': [{'price': {'id': 'price_t1_yr', 'recurring': {'interval': 'year'}}}]},
            })
        self.job.refresh_from_db()
        self.assertEqual(self.job.billing_interval, 'annual')

    def test_nonexistent_subscription_returns_silently(self):
        with patch('stripe_integration.webhook_handler.PRICE_TO_TIER', {}):
            self._handle({
                'id': 'sub_unknown', 'status': 'active',
                'items': {'data': [{'price': {'id': 'x'}}]},
            })


# ---------------------------------------------------------------------------
# customer.subscription.deleted
# ---------------------------------------------------------------------------

class SubscriptionDeletedTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.job = make_job(self.customer, stripe_subscription_id='sub_abc')

    def _handle(self, data_dict):
        from stripe_integration.webhook_handler import _handle_subscription_deleted
        _handle_subscription_deleted(_make_event('customer.subscription.deleted', data_dict))

    def test_sets_cancelled_status(self):
        self._handle({'id': 'sub_abc', 'status': 'canceled'})
        self.job.refresh_from_db()
        self.assertEqual(self.job.subscription_status, 'cancelled')

    def test_nonexistent_subscription_returns_silently(self):
        self._handle({'id': 'sub_unknown', 'status': 'canceled'})


# ---------------------------------------------------------------------------
# Unknown event type
# ---------------------------------------------------------------------------

class UnknownEventTests(TestCase):
    @patch('stripe_integration.views.stripe.Webhook.construct_event')
    def test_unknown_event_returns_200(self, mock_construct):
        mock_construct.return_value = _make_event('unknown.event.type', {})
        response = self.client.post(
            '/webhooks/stripe/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='sig',
        )
        self.assertEqual(response.status_code, 200)

    def test_unknown_event_raises_no_exception(self):
        from stripe_integration.webhook_handler import handle_stripe_event
        handle_stripe_event(_make_event('totally.unknown', {}))

    def test_unknown_event_makes_no_model_changes(self):
        customer = make_customer()
        job = make_job(customer)
        before_status = job.status

        from stripe_integration.webhook_handler import handle_stripe_event
        handle_stripe_event(_make_event('totally.unknown', {}))

        job.refresh_from_db()
        self.assertEqual(job.status, before_status)
