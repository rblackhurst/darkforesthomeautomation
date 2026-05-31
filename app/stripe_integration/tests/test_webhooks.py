import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory

from jobs.models import Customer, Job
from stripe_integration.models import InternalAlert


def make_customer(**kwargs):
    defaults = dict(first_name='Jane', last_name='Smith', email='jane@example.com')
    defaults.update(kwargs)
    return Customer.objects.create(**defaults)


def make_job(customer, **kwargs):
    defaults = dict(invoice_number='TEST-001')
    defaults.update(kwargs)
    return Job.objects.create(customer=customer, **defaults)


def _post_event(client, payload, sig='valid-sig'):
    return client.post(
        '/webhooks/stripe/',
        data=json.dumps(payload),
        content_type='application/json',
        HTTP_STRIPE_SIGNATURE=sig,
    )


def _make_event(event_type, data_object, event_id='evt_test'):
    return {
        'id': event_id,
        'type': event_type,
        'data': {'object': data_object},
    }


class WebhookSignatureTests(TestCase):
    def _valid_event(self):
        return _make_event('invoice.paid', {
            'id': 'in_1', 'metadata': {}, 'payment_intent': 'pi_1',
        })

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
        import stripe
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
        import stripe
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


class InvoicePaidDepositTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.job = make_job(self.customer, stripe_deposit_invoice_id='in_dep')

    def _handle(self, invoice_obj):
        from stripe_integration.webhook_handler import _handle_invoice_paid
        _handle_invoice_paid(_make_event('invoice.paid', invoice_obj))

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
        self._handle({'id': 'in_x', 'metadata': {}})  # no exception

    def test_nonexistent_job_id_returns_silently(self):
        self._handle({'id': 'in_x', 'metadata': {'dfha_job_id': 'NOPE-999', 'invoice_type': 'deposit'}})


class InvoicePaidFinalTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.job = make_job(self.customer, stripe_final_invoice_id='in_fin')

    def _handle(self, invoice_obj):
        from stripe_integration.webhook_handler import _handle_invoice_paid
        _handle_invoice_paid(_make_event('invoice.paid', invoice_obj))

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


class InvoicePaymentFailedTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.job = make_job(self.customer, stripe_deposit_invoice_id='in_dep')

    def _handle(self, invoice_obj, event_id='evt_1'):
        from stripe_integration.webhook_handler import _handle_invoice_payment_failed
        _handle_invoice_payment_failed(_make_event('invoice.payment_failed', invoice_obj, event_id=event_id))

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


class SubscriptionUpdatedTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.job = make_job(self.customer, stripe_subscription_id='sub_abc')

    def _handle(self, sub_obj):
        from stripe_integration.webhook_handler import _handle_subscription_updated
        _handle_subscription_updated(_make_event('customer.subscription.updated', sub_obj))

    def test_updates_subscription_status(self):
        with patch('stripe_integration.webhook_handler.PRICE_TO_TIER', {'price_t1': 'tier1'}):
            self._handle({
                'id': 'sub_abc', 'status': 'past_due',
                'items': {'data': [{'price': {'id': 'price_t1'}}]},
            })
        self.job.refresh_from_db()
        self.assertEqual(self.job.subscription_status, 'past_due')

    def test_updates_plan_tier(self):
        with patch('stripe_integration.webhook_handler.PRICE_TO_TIER', {'price_t2': 'tier2'}):
            self._handle({
                'id': 'sub_abc', 'status': 'active',
                'items': {'data': [{'price': {'id': 'price_t2'}}]},
            })
        self.job.refresh_from_db()
        self.assertEqual(self.job.plan_tier, 'tier2')

    def test_nonexistent_subscription_returns_silently(self):
        with patch('stripe_integration.webhook_handler.PRICE_TO_TIER', {}):
            self._handle({
                'id': 'sub_unknown', 'status': 'active',
                'items': {'data': [{'price': {'id': 'x'}}]},
            })  # no exception


class SubscriptionDeletedTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.job = make_job(self.customer, stripe_subscription_id='sub_abc')

    def _handle(self, sub_obj):
        from stripe_integration.webhook_handler import _handle_subscription_deleted
        _handle_subscription_deleted(_make_event('customer.subscription.deleted', sub_obj))

    def test_sets_cancelled_status(self):
        self._handle({'id': 'sub_abc', 'status': 'canceled'})
        self.job.refresh_from_db()
        self.assertEqual(self.job.subscription_status, 'cancelled')

    def test_nonexistent_subscription_returns_silently(self):
        self._handle({'id': 'sub_unknown', 'status': 'canceled'})  # no exception


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
        handle_stripe_event(_make_event('totally.unknown', {}))  # no exception

    def test_unknown_event_makes_no_model_changes(self):
        customer = make_customer()
        job = make_job(customer)
        before_status = job.status

        from stripe_integration.webhook_handler import handle_stripe_event
        handle_stripe_event(_make_event('totally.unknown', {}))

        job.refresh_from_db()
        self.assertEqual(job.status, before_status)
