from django.contrib.admin.sites import AdminSite
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from jobs.models import Customer, Job
from jobs.admin import JobAdmin

User = get_user_model()


def make_customer():
    return Customer.objects.create(
        first_name="Jane", last_name="Smith", email="jane@example.com"
    )


def make_job(customer, **kwargs):
    defaults = dict(invoice_number="TEST-001")
    defaults.update(kwargs)
    return Job.objects.create(customer=customer, **defaults)


class BillingIntervalFieldTests(TestCase):
    def setUp(self):
        self.customer = make_customer()

    def test_default_is_none(self):
        job = make_job(self.customer)
        self.assertEqual(job.billing_interval, "none")

    def test_accepts_monthly(self):
        job = make_job(self.customer, billing_interval="monthly")
        job.refresh_from_db()
        self.assertEqual(job.billing_interval, "monthly")

    def test_accepts_annual(self):
        job = make_job(self.customer, billing_interval="annual")
        job.refresh_from_db()
        self.assertEqual(job.billing_interval, "annual")

    def test_accepts_none(self):
        job = make_job(self.customer, billing_interval="none")
        job.refresh_from_db()
        self.assertEqual(job.billing_interval, "none")


class StripePaymentStatusPanelTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.site = AdminSite()
        self.ma = JobAdmin(Job, self.site)

    def test_no_stripe_data_returns_placeholder(self):
        job = make_job(self.customer)
        result = self.ma.stripe_payment_status_panel(job)
        self.assertIn("No Stripe payment activity recorded", str(result))

    def test_deposit_paid_shows_paid(self):
        job = make_job(self.customer,
                       deposit_paid=True,
                       stripe_deposit_invoice_id="in_dep123")
        result = str(self.ma.stripe_payment_status_panel(job))
        self.assertIn("Paid", result)
        self.assertIn("#2e7d32", result)

    def test_deposit_unpaid_shows_unpaid(self):
        job = make_job(self.customer,
                       deposit_paid=False,
                       stripe_deposit_invoice_id="in_dep123")
        result = str(self.ma.stripe_payment_status_panel(job))
        self.assertIn("Unpaid", result)

    def test_deposit_invoice_url_renders_link(self):
        job = make_job(self.customer,
                       stripe_deposit_invoice_url="https://invoice.stripe.com/i/dep",
                       stripe_deposit_invoice_id="in_dep123")
        result = str(self.ma.stripe_payment_status_panel(job))
        self.assertIn("https://invoice.stripe.com/i/dep", result)
        self.assertIn("Open in Stripe", result)

    def test_payment_failed_row_shown_when_true(self):
        job = make_job(self.customer,
                       payment_failed=True,
                       stripe_deposit_invoice_id="in_dep123")
        result = str(self.ma.stripe_payment_status_panel(job))
        self.assertIn("Payment failed", result)

    def test_payment_failed_row_absent_when_false(self):
        job = make_job(self.customer,
                       payment_failed=False,
                       stripe_deposit_invoice_id="in_dep123")
        result = str(self.ma.stripe_payment_status_panel(job))
        self.assertNotIn("Payment failed", result)


class StripeSubscriptionStatusPanelTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.site = AdminSite()
        self.ma = JobAdmin(Job, self.site)

    def test_no_subscription_id_returns_placeholder(self):
        job = make_job(self.customer)
        result = str(self.ma.stripe_subscription_status_panel(job))
        self.assertIn("No active subscription", result)

    def test_active_status_shows_green(self):
        job = make_job(self.customer,
                       stripe_subscription_id="sub_abc",
                       subscription_status="active",
                       service_plan_tier="tier1",
                       billing_interval="monthly")
        result = str(self.ma.stripe_subscription_status_panel(job))
        self.assertIn("#2e7d32", result)
        self.assertIn("Active", result)

    def test_past_due_status_renders(self):
        job = make_job(self.customer,
                       stripe_subscription_id="sub_abc",
                       subscription_status="past_due",
                       service_plan_tier="tier2",
                       billing_interval="monthly")
        result = str(self.ma.stripe_subscription_status_panel(job))
        self.assertIn("Past Due", result)

    def test_service_plan_display_label(self):
        job = make_job(self.customer,
                       stripe_subscription_id="sub_abc",
                       subscription_status="active",
                       service_plan_tier="tier3",
                       billing_interval="annual")
        result = str(self.ma.stripe_subscription_status_panel(job))
        self.assertIn("Premium", result)

    def test_billing_interval_display_label(self):
        job = make_job(self.customer,
                       stripe_subscription_id="sub_abc",
                       subscription_status="active",
                       service_plan_tier="tier2",
                       billing_interval="annual")
        result = str(self.ma.stripe_subscription_status_panel(job))
        self.assertIn("Annual", result)
