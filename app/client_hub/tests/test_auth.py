from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from jobs.models import Customer

from ..auth import generate_magic_link_token, validate_magic_link_token
from ..models import MagicLinkToken


class GenerateMagicLinkTokenTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            first_name='Alice', last_name='Auth', email='alice@auth.com'
        )

    @override_settings(MAGIC_LINK_EXPIRY_SECONDS=1200)
    def test_creates_token_with_correct_expiry(self):
        before = timezone.now()
        token_str = generate_magic_link_token(self.customer)
        after = timezone.now()

        token = MagicLinkToken.objects.get(token=token_str)
        self.assertEqual(token.customer, self.customer)
        self.assertIsNone(token.used_at)
        # expiry should be ~20 minutes from now
        self.assertGreater(token.expires_at, before + timedelta(seconds=1190))
        self.assertLess(token.expires_at, after + timedelta(seconds=1210))

    def test_second_token_invalidates_first(self):
        first = generate_magic_link_token(self.customer)
        second = generate_magic_link_token(self.customer)

        first_token = MagicLinkToken.objects.get(token=first)
        self.assertFalse(first_token.is_valid)

        second_token = MagicLinkToken.objects.get(token=second)
        self.assertTrue(second_token.is_valid)


class ValidateMagicLinkTokenTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            first_name='Bob', last_name='Auth', email='bob@auth.com'
        )

    def _make_token(self, **kwargs):
        defaults = dict(
            customer=self.customer,
            token='testtoken123',
            expires_at=timezone.now() + timedelta(minutes=20),
        )
        defaults.update(kwargs)
        return MagicLinkToken.objects.create(**defaults)

    def test_valid_token_returns_customer(self):
        self._make_token()
        result = validate_magic_link_token('testtoken123')
        self.assertEqual(result, self.customer)

    def test_valid_token_is_marked_used(self):
        self._make_token()
        validate_magic_link_token('testtoken123')
        token = MagicLinkToken.objects.get(token='testtoken123')
        self.assertIsNotNone(token.used_at)

    def test_expired_token_returns_none(self):
        self._make_token(expires_at=timezone.now() - timedelta(seconds=1))
        result = validate_magic_link_token('testtoken123')
        self.assertIsNone(result)

    def test_used_token_returns_none(self):
        self._make_token(used_at=timezone.now() - timedelta(minutes=5))
        result = validate_magic_link_token('testtoken123')
        self.assertIsNone(result)

    def test_nonexistent_token_returns_none(self):
        result = validate_magic_link_token('doesnotexist')
        self.assertIsNone(result)
