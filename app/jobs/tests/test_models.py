from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from jobs.models import Customer, Job, Property

User = get_user_model()


def make_customer(**kwargs):
    defaults = dict(first_name='Jane', last_name='Smith', email='jane@example.com')
    defaults.update(kwargs)
    return Customer.objects.create(**defaults)


def make_job(customer, **kwargs):
    defaults = dict(invoice_number='TEST-001')
    defaults.update(kwargs)
    return Job.objects.create(customer=customer, **defaults)


# ── Property model ────────────────────────────────────────────────────────────

class PropertyCreationTests(TestCase):
    def setUp(self):
        self.customer = make_customer()

    def test_signal_creates_primary_residence_on_customer_save(self):
        self.assertEqual(self.customer.properties.count(), 1)
        prop = self.customer.properties.first()
        self.assertEqual(prop.name, 'Primary Residence')

    def test_str(self):
        prop = self.customer.properties.first()
        result = str(prop)
        self.assertIn('Smith', result)
        self.assertIn('Primary Residence', result)

    def test_defaults(self):
        prop = self.customer.properties.first()
        self.assertEqual(prop.service_plan_tier, 'none')
        self.assertEqual(prop.billing_interval, 'none')
        self.assertEqual(prop.pending_subscription_price_id, '')
        self.assertIsNone(prop.stripe_subscription_id)
        self.assertIsNone(prop.subscription_status)

    def test_create_additional_property(self):
        Property.objects.create(customer=self.customer, name='Beach House')
        self.assertEqual(self.customer.properties.count(), 2)


class PropertySignalTests(TestCase):
    def test_signal_is_idempotent(self):
        customer = make_customer()
        # Creating the customer triggers the signal once.
        count_before = customer.properties.count()
        # Saving again (update, not create) must not create another property.
        customer.first_name = 'Janet'
        customer.save()
        self.assertEqual(customer.properties.count(), count_before)

    def test_signal_uses_get_or_create(self):
        customer = make_customer()
        # Even if there is already a "Primary Residence" property, a second
        # signal call should not create a duplicate.
        from jobs.models import create_primary_property
        create_primary_property(sender=Customer, instance=customer, created=True)
        self.assertEqual(customer.properties.count(), 1)


# ── Customer.email uniqueness ─────────────────────────────────────────────────

class CustomerEmailUniquenessTests(TestCase):
    def test_duplicate_email_raises(self):
        from django.db import IntegrityError
        make_customer(email='unique@example.com')
        with self.assertRaises(IntegrityError):
            make_customer(email='unique@example.com')

    def test_different_emails_allowed(self):
        make_customer(email='a@example.com')
        make_customer(email='b@example.com')
        self.assertEqual(Customer.objects.filter(email__contains='@example.com').count(), 2)


# ── Customer.user OneToOneField ───────────────────────────────────────────────

class CustomerUserLinkTests(TestCase):
    def test_customer_user_field_is_optional(self):
        customer = make_customer()
        self.assertIsNone(customer.user)

    def test_can_link_user_to_customer(self):
        customer = make_customer()
        user = User.objects.create_user(username='testuser', password='testpass')
        customer.user = user
        customer.save(update_fields=['user'])
        customer.refresh_from_db()
        self.assertEqual(customer.user, user)

    def test_related_name_customer_profile(self):
        customer = make_customer()
        user = User.objects.create_user(username='testuser2', password='testpass')
        customer.user = user
        customer.save(update_fields=['user'])
        self.assertEqual(user.customer_profile, customer)


# ── Job.property FK ───────────────────────────────────────────────────────────

class JobPropertyFKTests(TestCase):
    def test_job_property_defaults_to_null(self):
        customer = make_customer()
        job = make_job(customer)
        self.assertIsNone(job.property)

    def test_job_can_be_linked_to_property(self):
        customer = make_customer()
        prop = customer.properties.first()
        job = make_job(customer, property=prop)
        job.refresh_from_db()
        self.assertEqual(job.property, prop)

    def test_job_property_fk_is_nullable(self):
        customer = make_customer()
        job = make_job(customer)
        self.assertIsNone(job.property_id)

    def test_subscription_fields_not_on_job(self):
        job_instance = Job()
        self.assertFalse(hasattr(job_instance, 'service_plan_tier'))
        self.assertFalse(hasattr(job_instance, 'stripe_subscription_id'))
        self.assertFalse(hasattr(job_instance, 'subscription_status'))
        self.assertFalse(hasattr(job_instance, 'billing_interval'))
        self.assertFalse(hasattr(job_instance, 'pending_subscription_price_id'))
