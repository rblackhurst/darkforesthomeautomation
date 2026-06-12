from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from jobs.models import Customer

from ..models import MagicLinkToken, WorkRequest


class MagicLinkTokenIsValidTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            first_name='Alice', last_name='Test', email='alice@example.com'
        )

    def _make_token(self, **kwargs):
        defaults = dict(
            customer=self.customer,
            token='abc',
            expires_at=timezone.now() + timedelta(minutes=20),
        )
        defaults.update(kwargs)
        return MagicLinkToken.objects.create(**defaults)

    def test_valid_token(self):
        t = self._make_token()
        self.assertTrue(t.is_valid)

    def test_expired_token_is_not_valid(self):
        t = self._make_token(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(t.is_valid)

    def test_used_token_is_not_valid(self):
        t = self._make_token(used_at=timezone.now())
        self.assertFalse(t.is_valid)


class WorkRequestGetRequestTypesDisplayTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            first_name='Bob', last_name='Test', email='bob@example.com'
        )

    def test_single_type(self):
        wr = WorkRequest(
            customer=self.customer,
            request_types='new_install',
            description='test',
            contact_name='Bob Test',
            contact_email='bob@example.com',
        )
        self.assertEqual(wr.get_request_types_display(), 'New Installation')

    def test_multiple_types(self):
        wr = WorkRequest(
            customer=self.customer,
            request_types='new_install,update_automation',
            description='test',
            contact_name='Bob Test',
            contact_email='bob@example.com',
        )
        self.assertEqual(
            wr.get_request_types_display(),
            'New Installation, Update Existing Automation',
        )
