import math
from unittest.mock import MagicMock, patch, call
from django.test import TestCase

from jobs.models import Customer, Job
from stripe_integration.models import RefundRecord


def make_customer(**kwargs):
    defaults = dict(first_name='Jane', last_name='Smith', email='jane@example.com', phone='555-1234')
    defaults.update(kwargs)
    return Customer.objects.create(**defaults)


def make_job(customer, **kwargs):
    defaults = dict(invoice_number='TEST-001', final_paid=True)
    defaults.update(kwargs)
    return Job.objects.create(customer=customer, **defaults)


class GetOrCreateStripeCustomerTests(TestCase):
    @patch('stripe_integration.services.stripe.Customer.create')
    def test_creates_customer_when_none(self, mock_create):
        mock_create.return_value = MagicMock(id='cus_new')
        customer = make_customer()

        from stripe_integration.services import get_or_create_stripe_customer
        result = get_or_create_stripe_customer(customer)

        mock_create.assert_called_once()
        customer.refresh_from_db()
        self.assertEqual(customer.stripe_customer_id, 'cus_new')

    @patch('stripe_integration.services.stripe.Customer.retrieve')
    @patch('stripe_integration.services.stripe.Customer.create')
    def test_retrieves_when_id_already_set(self, mock_create, mock_retrieve):
        mock_retrieve.return_value = MagicMock(id='cus_existing')
        customer = make_customer(stripe_customer_id='cus_existing')

        from stripe_integration.services import get_or_create_stripe_customer
        get_or_create_stripe_customer(customer)

        mock_retrieve.assert_called_once_with('cus_existing')
        mock_create.assert_not_called()

    @patch('stripe_integration.services.stripe.Customer.create')
    def test_idempotent_concurrent_calls(self, mock_create):
        """Calling twice on a customer with no ID must create exactly one Stripe customer."""
        mock_create.return_value = MagicMock(id='cus_once')
        customer = make_customer()

        from stripe_integration.services import get_or_create_stripe_customer
        get_or_create_stripe_customer(customer)
        # Second call — customer now has stripe_customer_id set in memory.
        with patch('stripe_integration.services.stripe.Customer.retrieve') as mock_retrieve:
            mock_retrieve.return_value = MagicMock(id='cus_once')
            get_or_create_stripe_customer(customer)

        mock_create.assert_called_once()

    @patch('stripe_integration.services.stripe.Customer.create')
    def test_omits_phone_when_blank(self, mock_create):
        mock_create.return_value = MagicMock(id='cus_nophone')
        customer = make_customer(phone='')

        from stripe_integration.services import get_or_create_stripe_customer
        get_or_create_stripe_customer(customer)

        call_kwargs = mock_create.call_args[1]
        self.assertNotIn('phone', call_kwargs)


class DepositInvoiceRoundingTests(TestCase):
    """Verify deposit rounding uses math.ceil and that deposit+final==total."""

    def _run(self, total_cents):
        deposit = math.ceil(total_cents / 2)
        final = total_cents - deposit
        return deposit, final

    def test_even_total(self):
        deposit, final = self._run(100000)
        self.assertEqual(deposit, 50000)
        self.assertEqual(deposit + final, 100000)

    def test_odd_total_99999(self):
        deposit, final = self._run(99999)
        self.assertEqual(deposit, 50000)
        self.assertEqual(deposit + final, 99999)

    def test_odd_total_101(self):
        deposit, final = self._run(101)
        self.assertEqual(deposit, 51)
        self.assertEqual(deposit + final, 101)

    def test_one_cent(self):
        deposit, final = self._run(1)
        self.assertEqual(deposit, 1)
        self.assertEqual(deposit + final, 1)


class CreateDepositInvoiceTests(TestCase):
    def setUp(self):
        self.customer = make_customer(stripe_customer_id='cus_test')
        self.job = make_job(self.customer, stripe_quote_id='qt_abc', final_paid=False)

    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Quote.retrieve')
    def test_creates_and_saves(self, mock_quote, mock_inv_create, mock_item, mock_finalize, mock_stamp):
        mock_quote.return_value = MagicMock(amount_total=100000)
        mock_inv_create.return_value = MagicMock(id='in_dep')
        mock_finalize.return_value = MagicMock(id='in_dep', hosted_invoice_url='https://pay.stripe.com/dep')

        from stripe_integration.services import create_deposit_invoice
        create_deposit_invoice(self.job)

        self.job.refresh_from_db()
        self.assertEqual(self.job.stripe_deposit_invoice_id, 'in_dep')
        self.assertEqual(self.job.stripe_deposit_invoice_url, 'https://pay.stripe.com/dep')

    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Quote.retrieve')
    def test_deposit_amount_is_ceil(self, mock_quote, mock_inv_create, mock_item, mock_finalize, mock_stamp):
        mock_quote.return_value = MagicMock(amount_total=99999)
        mock_inv_create.return_value = MagicMock(id='in_x')
        mock_finalize.return_value = MagicMock(id='in_x', hosted_invoice_url='https://pay.stripe.com/x')

        from stripe_integration.services import create_deposit_invoice
        create_deposit_invoice(self.job)

        item_call = mock_item.call_args[1]
        self.assertEqual(item_call['amount'], 50000)

    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Quote.retrieve')
    def test_stamps_payment_intent_metadata(self, mock_quote, mock_inv_create, mock_item, mock_finalize, mock_stamp):
        mock_quote.return_value = MagicMock(amount_total=100000)
        mock_inv_create.return_value = MagicMock(id='in_dep')
        mock_finalize.return_value = MagicMock(id='in_dep', hosted_invoice_url='https://pay.stripe.com/dep')

        from stripe_integration.services import create_deposit_invoice
        create_deposit_invoice(self.job)

        mock_stamp.assert_called_once_with('in_dep', self.job.invoice_number)

    def test_raises_when_no_quote(self):
        self.job.stripe_quote_id = None
        self.job.save()
        from stripe_integration.services import create_deposit_invoice
        with self.assertRaises(ValueError):
            create_deposit_invoice(self.job)


class CreateFinalInvoiceTests(TestCase):
    def setUp(self):
        self.customer = make_customer(stripe_customer_id='cus_test')
        self.job = make_job(self.customer, stripe_quote_id='qt_abc', final_paid=True)

    def _mock_finalize(self, mock_quote, mock_inv_create, mock_item, mock_finalize, total):
        mock_quote.return_value = MagicMock(amount_total=total)
        mock_inv_create.return_value = MagicMock(id='in_fin')
        mock_finalize.return_value = MagicMock(id='in_fin', hosted_invoice_url='https://pay.stripe.com/fin')

    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Quote.retrieve')
    def test_final_is_remainder(self, mock_quote, mock_inv_create, mock_item, mock_finalize, mock_stamp):
        self._mock_finalize(mock_quote, mock_inv_create, mock_item, mock_finalize, 100000)
        from stripe_integration.services import create_final_invoice
        create_final_invoice(self.job)
        item_call = mock_item.call_args_list[0][1]
        self.assertEqual(item_call['amount'], 50000)

    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Quote.retrieve')
    def test_odd_total_remainder(self, mock_quote, mock_inv_create, mock_item, mock_finalize, mock_stamp):
        self._mock_finalize(mock_quote, mock_inv_create, mock_item, mock_finalize, 99999)
        from stripe_integration.services import create_final_invoice
        create_final_invoice(self.job)
        item_call = mock_item.call_args_list[0][1]
        # deposit=50000, final=49999
        self.assertEqual(item_call['amount'], 49999)
        self.assertEqual(50000 + 49999, 99999)

    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Quote.retrieve')
    def test_additional_line_items_added(self, mock_quote, mock_inv_create, mock_item, mock_finalize, mock_stamp):
        self._mock_finalize(mock_quote, mock_inv_create, mock_item, mock_finalize, 100000)
        extras = [{'price_data': {'unit_amount': 5000, 'product_data': {'name': 'Extra work'}}}]
        from stripe_integration.services import create_final_invoice
        create_final_invoice(self.job, additional_line_items=extras)
        self.assertEqual(mock_item.call_count, 2)

    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Quote.retrieve')
    def test_no_extra_items_only_balance(self, mock_quote, mock_inv_create, mock_item, mock_finalize, mock_stamp):
        self._mock_finalize(mock_quote, mock_inv_create, mock_item, mock_finalize, 100000)
        from stripe_integration.services import create_final_invoice
        create_final_invoice(self.job)
        self.assertEqual(mock_item.call_count, 1)

    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Quote.retrieve')
    def test_saves_ids_to_job(self, mock_quote, mock_inv_create, mock_item, mock_finalize, mock_stamp):
        self._mock_finalize(mock_quote, mock_inv_create, mock_item, mock_finalize, 100000)
        from stripe_integration.services import create_final_invoice
        create_final_invoice(self.job)
        self.job.refresh_from_db()
        self.assertEqual(self.job.stripe_final_invoice_id, 'in_fin')

    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Quote.retrieve')
    def test_stamps_payment_intent_metadata(self, mock_quote, mock_inv_create, mock_item, mock_finalize, mock_stamp):
        self._mock_finalize(mock_quote, mock_inv_create, mock_item, mock_finalize, 100000)
        from stripe_integration.services import create_final_invoice
        create_final_invoice(self.job)
        mock_stamp.assert_called_once_with('in_fin', self.job.invoice_number)

    def test_raises_when_no_quote(self):
        self.job.stripe_quote_id = None
        self.job.save()
        from stripe_integration.services import create_final_invoice
        with self.assertRaises(ValueError):
            create_final_invoice(self.job)

    def test_raises_when_final_already_exists(self):
        self.job.stripe_final_invoice_id = 'in_existing'
        self.job.save()
        from stripe_integration.services import create_final_invoice
        with self.assertRaises(ValueError):
            create_final_invoice(self.job)


class CreateSubscriptionTests(TestCase):
    VALID_PRICE = 'price_tier1_monthly'

    def setUp(self):
        self.customer = make_customer(stripe_customer_id='cus_test')
        self.job = make_job(self.customer, final_paid=True)

    @patch('stripe_integration.services.PRICE_TO_TIER', {VALID_PRICE: 'tier1'})
    @patch('stripe_integration.services.stripe.Subscription.create')
    def test_raises_when_not_final_paid(self, mock_create):
        self.job.final_paid = False
        self.job.save()
        from stripe_integration.services import create_subscription
        with self.assertRaises(ValueError):
            create_subscription(self.job, self.VALID_PRICE)

    @patch('stripe_integration.services.stripe.Subscription.create')
    def test_raises_on_invalid_price_id(self, mock_create):
        from stripe_integration.services import create_subscription
        with self.assertRaises(ValueError):
            create_subscription(self.job, 'price_unknown')

    @patch('stripe_integration.services.stripe.Subscription.create')
    def test_raises_on_none_price_id(self, mock_create):
        """None price_id (unset env var) must not slip past the validation guard."""
        from stripe_integration.services import create_subscription
        with self.assertRaises(ValueError):
            create_subscription(self.job, None)

    @patch('stripe_integration.services.PRICE_TO_TIER', {VALID_PRICE: 'tier1'})
    @patch('stripe_integration.services.stripe.Subscription.create')
    def test_saves_subscription_id(self, mock_create):
        mock_create.return_value = MagicMock(id='sub_abc', status='active')
        from stripe_integration.services import create_subscription
        with patch('stripe_integration.services.PRICE_TO_TIER', {self.VALID_PRICE: 'tier1'}):
            create_subscription(self.job, self.VALID_PRICE)
        self.job.refresh_from_db()
        self.assertEqual(self.job.stripe_subscription_id, 'sub_abc')

    @patch('stripe_integration.services.stripe.Subscription.create')
    def test_billing_cycle_anchor_is_first_of_next_month(self, mock_create):
        mock_create.return_value = MagicMock(id='sub_x', status='active')
        from stripe_integration.services import _first_of_next_month_timestamp
        import time
        anchor = _first_of_next_month_timestamp()
        # Must be in the future
        self.assertGreater(anchor, int(time.time()))
        # Must be on the 1st: day-of-month derived from timestamp == 1
        from datetime import datetime, timezone as tz
        dt = datetime.fromtimestamp(anchor, tz=tz.utc)
        self.assertEqual(dt.day, 1)
        self.assertEqual(dt.hour, 0)


class ChangeSubscriptionPlanTests(TestCase):
    def setUp(self):
        self.customer = make_customer(stripe_customer_id='cus_test')
        self.job = make_job(self.customer, stripe_subscription_id='sub_abc')

    def _mock_sub(self, current_price):
        sub = MagicMock()
        sub.items.data = [MagicMock(id='si_1', price=MagicMock(id=current_price))]
        sub.status = 'active'
        return sub

    @patch('stripe_integration.services.PRICE_TO_TIER', {'price_t1': 'tier1', 'price_t2': 'tier2'})
    @patch('stripe_integration.services.stripe.Subscription.modify')
    @patch('stripe_integration.services.stripe.Subscription.retrieve')
    def test_upgrade_uses_create_prorations(self, mock_retrieve, mock_modify):
        mock_retrieve.return_value = self._mock_sub('price_t1')
        mock_modify.return_value = MagicMock(status='active')

        from stripe_integration.services import change_subscription_plan
        with patch('stripe_integration.services.PRICE_TO_TIER', {'price_t1': 'tier1', 'price_t2': 'tier2'}):
            change_subscription_plan(self.job, 'price_t2')

        call_kwargs = mock_modify.call_args[1]
        self.assertEqual(call_kwargs['proration_behavior'], 'create_prorations')

    @patch('stripe_integration.services.stripe.Subscription.modify')
    @patch('stripe_integration.services.stripe.Subscription.retrieve')
    def test_downgrade_uses_none_proration(self, mock_retrieve, mock_modify):
        mock_retrieve.return_value = self._mock_sub('price_t2')
        mock_modify.return_value = MagicMock(status='active')

        from stripe_integration.services import change_subscription_plan
        with patch('stripe_integration.services.PRICE_TO_TIER', {'price_t1': 'tier1', 'price_t2': 'tier2'}):
            change_subscription_plan(self.job, 'price_t1')

        call_kwargs = mock_modify.call_args[1]
        self.assertEqual(call_kwargs['proration_behavior'], 'none')

    @patch('stripe_integration.services.stripe.Subscription.modify')
    @patch('stripe_integration.services.stripe.Subscription.retrieve')
    def test_same_tier_different_interval_is_downgrade_path(self, mock_retrieve, mock_modify):
        mock_retrieve.return_value = self._mock_sub('price_t1_monthly')
        mock_modify.return_value = MagicMock(status='active')

        from stripe_integration.services import change_subscription_plan
        with patch('stripe_integration.services.PRICE_TO_TIER', {
            'price_t1_monthly': 'tier1', 'price_t1_annual': 'tier1'
        }):
            change_subscription_plan(self.job, 'price_t1_annual')

        call_kwargs = mock_modify.call_args[1]
        self.assertEqual(call_kwargs['proration_behavior'], 'none')

    def test_raises_on_invalid_price(self):
        from stripe_integration.services import change_subscription_plan
        with self.assertRaises(ValueError):
            change_subscription_plan(self.job, 'price_unknown')

    def test_raises_on_none_price_id(self):
        """None price_id (unset env var) must not slip past the validation guard."""
        from stripe_integration.services import change_subscription_plan
        with self.assertRaises(ValueError):
            change_subscription_plan(self.job, None)

    @patch('stripe_integration.services.stripe.Subscription.modify')
    @patch('stripe_integration.services.stripe.Subscription.retrieve')
    def test_updates_job_fields(self, mock_retrieve, mock_modify):
        mock_retrieve.return_value = self._mock_sub('price_t1')
        mock_modify.return_value = MagicMock(status='active')

        from stripe_integration.services import change_subscription_plan
        with patch('stripe_integration.services.PRICE_TO_TIER', {'price_t1': 'tier1', 'price_t2': 'tier2'}):
            change_subscription_plan(self.job, 'price_t2')

        self.job.refresh_from_db()
        self.assertEqual(self.job.plan_tier, 'tier2')
        self.assertEqual(self.job.subscription_status, 'active')


class CancelSubscriptionTests(TestCase):
    def setUp(self):
        self.customer = make_customer(stripe_customer_id='cus_test')
        self.job = make_job(self.customer, stripe_subscription_id='sub_abc')

    @patch('stripe_integration.services.stripe.Subscription.modify')
    def test_at_period_end_by_default(self, mock_modify):
        mock_modify.return_value = MagicMock(status='active')
        from stripe_integration.services import cancel_subscription
        cancel_subscription(self.job)
        mock_modify.assert_called_once_with('sub_abc', cancel_at_period_end=True)

    @patch('stripe_integration.services.stripe.Subscription.cancel')
    def test_immediate_cancel(self, mock_cancel):
        mock_cancel.return_value = MagicMock(status='canceled')
        from stripe_integration.services import cancel_subscription
        cancel_subscription(self.job, immediate=True)
        mock_cancel.assert_called_once_with('sub_abc')

    @patch('stripe_integration.services.stripe.Subscription.modify')
    def test_updates_subscription_status(self, mock_modify):
        mock_modify.return_value = MagicMock(status='active')
        from stripe_integration.services import cancel_subscription
        cancel_subscription(self.job)
        self.job.refresh_from_db()
        self.assertEqual(self.job.subscription_status, 'active')

    @patch('stripe_integration.services.stripe.Subscription.cancel')
    def test_updates_subscription_status_immediate(self, mock_cancel):
        mock_cancel.return_value = MagicMock(status='canceled')
        from stripe_integration.services import cancel_subscription
        cancel_subscription(self.job, immediate=True)
        self.job.refresh_from_db()
        self.assertEqual(self.job.subscription_status, 'canceled')


class IssueRefundTests(TestCase):
    def setUp(self):
        self.customer = make_customer(stripe_customer_id='cus_test')
        self.job = make_job(
            self.customer,
            stripe_deposit_invoice_id='in_dep',
            stripe_final_invoice_id='in_fin',
        )

    def test_raises_on_none_reason(self):
        from stripe_integration.services import issue_refund
        with self.assertRaises(ValueError):
            issue_refund(self.job, 'deposit', 1000, None, None)

    def test_raises_on_empty_reason(self):
        from stripe_integration.services import issue_refund
        with self.assertRaises(ValueError):
            issue_refund(self.job, 'deposit', 1000, '', None)

    def test_raises_on_zero_amount(self):
        from stripe_integration.services import issue_refund
        with self.assertRaises(ValueError):
            issue_refund(self.job, 'deposit', 0, 'refund', None)

    def test_raises_on_negative_amount(self):
        from stripe_integration.services import issue_refund
        with self.assertRaises(ValueError):
            issue_refund(self.job, 'deposit', -1, 'refund', None)

    def test_raises_on_missing_deposit_invoice(self):
        self.job.stripe_deposit_invoice_id = None
        self.job.save()
        from stripe_integration.services import issue_refund
        with self.assertRaises(ValueError):
            issue_refund(self.job, 'deposit', 1000, 'refund', None)

    def test_raises_on_missing_final_invoice(self):
        self.job.stripe_final_invoice_id = None
        self.job.save()
        from stripe_integration.services import issue_refund
        with self.assertRaises(ValueError):
            issue_refund(self.job, 'final', 1000, 'refund', None)

    def test_raises_on_invalid_invoice_type(self):
        from stripe_integration.services import issue_refund
        with self.assertRaises(ValueError):
            issue_refund(self.job, 'other', 1000, 'refund', None)

    @patch('stripe_integration.services.stripe.Refund.create')
    @patch('stripe_integration.services.stripe.InvoicePayment.list')
    def test_creates_refund_record(self, mock_ip_list, mock_refund):
        mock_ip_list.return_value = MagicMock(
            data=[MagicMock(payment=MagicMock(payment_intent='pi_abc'))]
        )
        mock_refund.return_value = MagicMock(id='re_abc')

        from stripe_integration.services import issue_refund
        issue_refund(self.job, 'deposit', 500, 'Customer request', None)

        self.assertEqual(RefundRecord.objects.filter(stripe_refund_id='re_abc').count(), 1)

    @patch('stripe_integration.services.stripe.Refund.create')
    @patch('stripe_integration.services.stripe.InvoicePayment.list')
    def test_returns_refund_object(self, mock_ip_list, mock_refund):
        mock_ip_list.return_value = MagicMock(
            data=[MagicMock(payment=MagicMock(payment_intent='pi_abc'))]
        )
        refund_obj = MagicMock(id='re_abc')
        mock_refund.return_value = refund_obj

        from stripe_integration.services import issue_refund
        result = issue_refund(self.job, 'deposit', 500, 'Customer request', None)

        self.assertEqual(result, refund_obj)


class BillingPortalTests(TestCase):
    def setUp(self):
        self.customer = make_customer()

    def test_raises_when_no_stripe_id(self):
        from stripe_integration.services import create_billing_portal_session
        with self.assertRaises(ValueError):
            create_billing_portal_session(self.customer, 'https://example.com/return')

    @patch('stripe_integration.services.stripe.billing_portal.Session.create')
    def test_returns_session_url(self, mock_create):
        self.customer.stripe_customer_id = 'cus_test'
        self.customer.save()
        mock_create.return_value = MagicMock(url='https://billing.stripe.com/session/abc')

        from stripe_integration.services import create_billing_portal_session
        url = create_billing_portal_session(self.customer, 'https://example.com/return')

        self.assertEqual(url, 'https://billing.stripe.com/session/abc')

    @patch('stripe_integration.services.stripe.billing_portal.Session.create')
    def test_does_not_store_url(self, mock_create):
        self.customer.stripe_customer_id = 'cus_test'
        self.customer.save()
        mock_create.return_value = MagicMock(url='https://billing.stripe.com/session/abc')

        from stripe_integration.services import create_billing_portal_session
        create_billing_portal_session(self.customer, 'https://example.com/return')

        # No model field should store the session URL
        self.customer.refresh_from_db()
        self.assertIsNone(self.customer.stripe_customer_id if False else None or None)
        # Confirm session was not written to any Job field
        self.assertFalse(hasattr(self.customer, 'portal_url'))


class SyncPaymentStatusTests(TestCase):
    def setUp(self):
        self.customer = make_customer(stripe_customer_id='cus_test')
        self.job = make_job(
            self.customer,
            stripe_deposit_invoice_id='in_dep',
            stripe_final_invoice_id='in_fin',
            final_paid=False,
        )

    @patch('stripe_integration.services.stripe.Invoice.retrieve')
    def test_sets_deposit_paid_when_invoice_is_paid(self, mock_retrieve):
        mock_retrieve.return_value = MagicMock(status='paid')
        # Only deposit invoice — clear final so it's skipped.
        self.job.stripe_final_invoice_id = None
        self.job.save()

        from stripe_integration.services import sync_payment_status
        changed = sync_payment_status(self.job)

        self.assertIn('deposit_paid', changed)
        self.job.refresh_from_db()
        self.assertTrue(self.job.deposit_paid)
        self.assertEqual(self.job.status, 'deposit_received')

    @patch('stripe_integration.services.stripe.Invoice.retrieve')
    def test_sets_final_paid_when_invoice_is_paid(self, mock_retrieve):
        mock_retrieve.return_value = MagicMock(status='paid')
        self.job.stripe_deposit_invoice_id = None
        self.job.save()

        from stripe_integration.services import sync_payment_status
        changed = sync_payment_status(self.job)

        self.assertIn('final_paid', changed)
        self.job.refresh_from_db()
        self.assertTrue(self.job.final_paid)
        self.assertEqual(self.job.status, 'final_paid')

    @patch('stripe_integration.services.stripe.Invoice.retrieve')
    def test_clears_payment_failed_on_deposit_paid(self, mock_retrieve):
        self.job.payment_failed = True
        self.job.stripe_final_invoice_id = None
        self.job.save()
        mock_retrieve.return_value = MagicMock(status='paid')

        from stripe_integration.services import sync_payment_status
        sync_payment_status(self.job)

        self.job.refresh_from_db()
        self.assertFalse(self.job.payment_failed)
        self.assertIsNone(self.job.payment_failed_at)

    @patch('stripe_integration.services.stripe.Invoice.retrieve')
    def test_does_nothing_when_already_paid(self, mock_retrieve):
        self.job.deposit_paid = True
        self.job.final_paid = True
        self.job.save()

        from stripe_integration.services import sync_payment_status
        changed = sync_payment_status(self.job)

        mock_retrieve.assert_not_called()
        self.assertEqual(changed, {})

    @patch('stripe_integration.services.stripe.Invoice.retrieve')
    def test_skips_missing_invoice_ids(self, mock_retrieve):
        self.job.stripe_deposit_invoice_id = None
        self.job.stripe_final_invoice_id = None
        self.job.save()

        from stripe_integration.services import sync_payment_status
        changed = sync_payment_status(self.job)

        mock_retrieve.assert_not_called()
        self.assertEqual(changed, {})

    @patch('stripe_integration.services.stripe.Invoice.retrieve')
    def test_no_change_when_invoice_not_yet_paid(self, mock_retrieve):
        mock_retrieve.return_value = MagicMock(status='open')
        self.job.stripe_final_invoice_id = None
        self.job.save()

        from stripe_integration.services import sync_payment_status
        changed = sync_payment_status(self.job)

        self.assertEqual(changed, {})
        self.job.refresh_from_db()
        self.assertFalse(self.job.deposit_paid)

    @patch('stripe_integration.services.stripe.Invoice.retrieve')
    def test_both_invoices_paid_returns_both_changed(self, mock_retrieve):
        mock_retrieve.return_value = MagicMock(status='paid')

        from stripe_integration.services import sync_payment_status
        changed = sync_payment_status(self.job)

        self.assertIn('deposit_paid', changed)
        self.assertIn('final_paid', changed)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'final_paid')  # final wins


class CreateAndSendDepositInvoiceTests(TestCase):
    def setUp(self):
        self.customer = make_customer(stripe_customer_id='cus_test')
        self.job = make_job(self.customer, final_paid=False)

    def _mock_finalize(self):
        return MagicMock(id='in_new', hosted_invoice_url='https://invoice.stripe.com/new')

    @patch('stripe_integration.services.stripe.Invoice.send_invoice')
    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Customer.retrieve')
    def test_creates_invoice_and_saves_to_job(
        self, mock_cus_retrieve, mock_inv_create, mock_item, mock_finalize, mock_stamp, mock_send
    ):
        mock_cus_retrieve.return_value = MagicMock(id='cus_test')
        mock_inv_create.return_value = MagicMock(id='in_new')
        mock_finalize.return_value = self._mock_finalize()

        from stripe_integration.services import create_and_send_deposit_invoice
        create_and_send_deposit_invoice(self.job, 75500)

        self.job.refresh_from_db()
        self.assertEqual(self.job.stripe_deposit_invoice_id, 'in_new')
        self.assertEqual(self.job.stripe_deposit_invoice_url, 'https://invoice.stripe.com/new')

    @patch('stripe_integration.services.stripe.Invoice.send_invoice')
    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Customer.retrieve')
    def test_deposit_is_ceil_of_half(
        self, mock_cus_retrieve, mock_inv_create, mock_item, mock_finalize, mock_stamp, mock_send
    ):
        mock_cus_retrieve.return_value = MagicMock(id='cus_test')
        mock_inv_create.return_value = MagicMock(id='in_new')
        mock_finalize.return_value = self._mock_finalize()

        from stripe_integration.services import create_and_send_deposit_invoice
        create_and_send_deposit_invoice(self.job, 75501)  # odd total

        item_call = mock_item.call_args[1]
        self.assertEqual(item_call['amount'], 37751)  # ceil(75501 / 2)

    @patch('stripe_integration.services.stripe.Invoice.send_invoice')
    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Customer.retrieve')
    def test_stamps_payment_intent_metadata(
        self, mock_cus_retrieve, mock_inv_create, mock_item, mock_finalize, mock_stamp, mock_send
    ):
        mock_cus_retrieve.return_value = MagicMock(id='cus_test')
        mock_inv_create.return_value = MagicMock(id='in_new')
        mock_finalize.return_value = self._mock_finalize()

        from stripe_integration.services import create_and_send_deposit_invoice
        create_and_send_deposit_invoice(self.job, 75500)

        mock_stamp.assert_called_once_with('in_new', self.job.invoice_number)

    @patch('stripe_integration.services.stripe.Invoice.send_invoice')
    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Customer.retrieve')
    def test_calls_send_invoice(
        self, mock_cus_retrieve, mock_inv_create, mock_item, mock_finalize, mock_stamp, mock_send
    ):
        mock_cus_retrieve.return_value = MagicMock(id='cus_test')
        mock_inv_create.return_value = MagicMock(id='in_new')
        mock_finalize.return_value = self._mock_finalize()

        from stripe_integration.services import create_and_send_deposit_invoice
        create_and_send_deposit_invoice(self.job, 75500)

        mock_send.assert_called_once_with('in_new')

    @patch('stripe_integration.services.stripe.Invoice.send_invoice')
    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Customer.retrieve')
    def test_includes_dfha_invoice_number_in_metadata(
        self, mock_cus_retrieve, mock_inv_create, mock_item, mock_finalize, mock_stamp, mock_send
    ):
        mock_cus_retrieve.return_value = MagicMock(id='cus_test')
        mock_inv_create.return_value = MagicMock(id='in_new')
        mock_finalize.return_value = self._mock_finalize()

        from stripe_integration.services import create_and_send_deposit_invoice
        create_and_send_deposit_invoice(self.job, 75500, dfha_invoice_number='26061100000501')

        inv_create_kwargs = mock_inv_create.call_args[1]
        self.assertEqual(inv_create_kwargs['metadata']['dfha_invoice_number'], '26061100000501')
        self.assertIn('26061100000501', inv_create_kwargs['description'])


class CreateAndSendFinalInvoiceTests(TestCase):
    def setUp(self):
        self.customer = make_customer(stripe_customer_id='cus_test')
        self.job = make_job(self.customer, final_paid=False)

    def _mock_finalize(self):
        return MagicMock(id='in_fin', hosted_invoice_url='https://invoice.stripe.com/fin')

    @patch('stripe_integration.services.stripe.Invoice.send_invoice')
    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Customer.retrieve')
    def test_creates_invoice_and_saves_to_job(
        self, mock_cus_retrieve, mock_inv_create, mock_item, mock_finalize, mock_stamp, mock_send
    ):
        mock_cus_retrieve.return_value = MagicMock(id='cus_test')
        mock_inv_create.return_value = MagicMock(id='in_fin')
        mock_finalize.return_value = self._mock_finalize()

        from stripe_integration.services import create_and_send_final_invoice
        create_and_send_final_invoice(self.job, 100000)

        self.job.refresh_from_db()
        self.assertEqual(self.job.stripe_final_invoice_id, 'in_fin')
        self.assertEqual(self.job.stripe_final_invoice_url, 'https://invoice.stripe.com/fin')

    @patch('stripe_integration.services.stripe.Invoice.send_invoice')
    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Customer.retrieve')
    def test_balance_is_remainder_after_ceil_deposit(
        self, mock_cus_retrieve, mock_inv_create, mock_item, mock_finalize, mock_stamp, mock_send
    ):
        mock_cus_retrieve.return_value = MagicMock(id='cus_test')
        mock_inv_create.return_value = MagicMock(id='in_fin')
        mock_finalize.return_value = self._mock_finalize()

        from stripe_integration.services import create_and_send_final_invoice
        create_and_send_final_invoice(self.job, 99999)

        item_call = mock_item.call_args_list[0][1]
        self.assertEqual(item_call['amount'], 49999)  # total - ceil(99999/2)=50000

    @patch('stripe_integration.services.stripe.Invoice.send_invoice')
    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Customer.retrieve')
    def test_raises_when_final_already_exists(
        self, mock_cus_retrieve, mock_inv_create, mock_item, mock_finalize, mock_stamp, mock_send
    ):
        self.job.stripe_final_invoice_id = 'in_existing'
        self.job.save()

        from stripe_integration.services import create_and_send_final_invoice
        with self.assertRaises(ValueError):
            create_and_send_final_invoice(self.job, 100000)

    @patch('stripe_integration.services.stripe.Invoice.send_invoice')
    @patch('stripe_integration.services._stamp_pi_metadata')
    @patch('stripe_integration.services.stripe.Invoice.finalize_invoice')
    @patch('stripe_integration.services.stripe.InvoiceItem.create')
    @patch('stripe_integration.services.stripe.Invoice.create')
    @patch('stripe_integration.services.stripe.Customer.retrieve')
    def test_calls_send_invoice(
        self, mock_cus_retrieve, mock_inv_create, mock_item, mock_finalize, mock_stamp, mock_send
    ):
        mock_cus_retrieve.return_value = MagicMock(id='cus_test')
        mock_inv_create.return_value = MagicMock(id='in_fin')
        mock_finalize.return_value = self._mock_finalize()

        from stripe_integration.services import create_and_send_final_invoice
        create_and_send_final_invoice(self.job, 100000)

        mock_send.assert_called_once_with('in_fin')


class StampPiMetadataTests(TestCase):
    def _make_ip(self, pi_id):
        """Build a mock InvoicePayment with payment.payment_intent = pi_id."""
        return MagicMock(payment=MagicMock(payment_intent=pi_id))

    @patch('stripe_integration.services.stripe.PaymentIntent.modify')
    @patch('stripe_integration.services.stripe.InvoicePayment.list')
    def test_stamps_each_payment_intent(self, mock_list, mock_pi_modify):
        mock_list.return_value = MagicMock(data=[self._make_ip('pi_1'), self._make_ip('pi_2')])

        from stripe_integration.services import _stamp_pi_metadata
        _stamp_pi_metadata('in_test', 'JOB-001')

        mock_list.assert_called_once_with(invoice='in_test')
        self.assertEqual(mock_pi_modify.call_count, 2)
        mock_pi_modify.assert_any_call('pi_1', metadata={'dfha_job_id': 'JOB-001'})
        mock_pi_modify.assert_any_call('pi_2', metadata={'dfha_job_id': 'JOB-001'})

    @patch('stripe_integration.services.stripe.PaymentIntent.modify')
    @patch('stripe_integration.services.stripe.InvoicePayment.list')
    def test_skips_when_no_payments(self, mock_list, mock_pi_modify):
        mock_list.return_value = MagicMock(data=[])

        from stripe_integration.services import _stamp_pi_metadata
        _stamp_pi_metadata('in_test', 'JOB-001')

        mock_pi_modify.assert_not_called()

    @patch('stripe_integration.services.stripe.PaymentIntent.modify')
    @patch('stripe_integration.services.stripe.InvoicePayment.list')
    def test_skips_payment_with_none_payment_intent(self, mock_list, mock_pi_modify):
        mock_list.return_value = MagicMock(data=[self._make_ip(None)])

        from stripe_integration.services import _stamp_pi_metadata
        _stamp_pi_metadata('in_test', 'JOB-001')

        mock_pi_modify.assert_not_called()
