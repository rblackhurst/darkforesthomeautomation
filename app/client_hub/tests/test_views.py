from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from client_credentials.models import (
    CredentialAccessLog,
    CredentialDeletionRequest,
    Device,
    DeviceCredential,
    InstalledSystem,
    SystemCredential,
)
from jobs.models import Customer, Property

from ..auth import generate_magic_link_token
from ..models import MagicLinkToken, ServicePlanChangeRequest, WorkRequest

User = get_user_model()

PORTAL_HOST = 'portal.darkforesthomeautomation.com'


# Apply portal host + ALLOWED_HOSTS to every request in this test class.
@override_settings(
    ALLOWED_HOSTS=['portal.darkforesthomeautomation.com', 'testserver', 'localhost', '127.0.0.1'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class AuthViewTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            first_name='Carol', last_name='View', email='carol@view.com'
        )
        # System user needed for credential logging
        self.system_user = User.objects.create_user(
            username='system', password='x', email='system@dfha.internal'
        )

    def _get(self, url_name, **kwargs):
        return self.client.get(
            reverse(url_name, **kwargs),
            HTTP_HOST=PORTAL_HOST,
        )

    def _post(self, url_name, data, kwargs=None):
        return self.client.post(
            reverse(url_name, **(kwargs or {})),
            data,
            HTTP_HOST=PORTAL_HOST,
        )

    def _login(self):
        session = self.client.session
        session['customer_id'] = self.customer.id
        session.save()

    # ── unauthenticated redirect ──────────────────────────────────────────────

    def test_dashboard_unauthenticated_redirects_to_login(self):
        resp = self._get('client_hub:dashboard')
        self.assertRedirects(
            resp,
            reverse('client_hub:login'),
            fetch_redirect_response=False,
        )

    # ── login views ───────────────────────────────────────────────────────────

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_login_unknown_email_redirects_to_login_sent(self):
        resp = self._post('client_hub:login', {'email': 'nobody@nowhere.com'})
        self.assertRedirects(
            resp, reverse('client_hub:login_sent'), fetch_redirect_response=False
        )
        self.assertEqual(MagicLinkToken.objects.count(), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_login_known_email_redirects_to_login_sent(self):
        resp = self._post('client_hub:login', {'email': self.customer.email})
        self.assertRedirects(
            resp, reverse('client_hub:login_sent'), fetch_redirect_response=False
        )
        self.assertEqual(MagicLinkToken.objects.count(), 1)

    def test_valid_token_sets_session_and_redirects_to_dashboard(self):
        token_str = generate_magic_link_token(self.customer)
        resp = self.client.get(
            reverse('client_hub:login_verify', kwargs={'token': token_str}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertRedirects(
            resp, reverse('client_hub:dashboard'), fetch_redirect_response=False
        )
        self.assertEqual(self.client.session.get('customer_id'), self.customer.id)

    def test_expired_token_shows_error(self):
        MagicLinkToken.objects.create(
            customer=self.customer,
            token='expiredtok',
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        resp = self.client.get(
            reverse('client_hub:login_verify', kwargs={'token': 'expiredtok'}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'invalid')

    # ── data isolation ────────────────────────────────────────────────────────

    def test_customer_cannot_access_another_customers_property(self):
        other = Customer.objects.create(
            first_name='Other', last_name='Person', email='other@view.com'
        )
        other_prop = Property.objects.filter(customer=other).first()
        self._login()
        resp = self.client.get(
            reverse('client_hub:property_detail', kwargs={'pk': other_prop.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 404)

    @override_settings(SYSTEM_USER_ID=None)
    def test_customer_cannot_access_another_customers_credential(self):
        other = Customer.objects.create(
            first_name='Other2', last_name='Person', email='other2@view.com'
        )
        other_prop = Property.objects.filter(customer=other).first()
        system = InstalledSystem.objects.create(
            property=other_prop,
            system_type='lighting',
            name='Other Lights',
        )
        cred = SystemCredential.objects.create(
            system=system,
            label='Router',
            username='admin',
            password='secret',
        )
        self._login()
        resp = self.client.get(
            reverse('client_hub:system_credential_detail', kwargs={'pk': cred.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 404)

    # ── credential detail ─────────────────────────────────────────────────────

    @override_settings(SYSTEM_USER_ID=None)
    def test_credential_detail_creates_access_log(self):
        prop = Property.objects.filter(customer=self.customer).first()
        system = InstalledSystem.objects.create(
            property=prop, system_type='networking', name='Test System',
        )
        cred = SystemCredential.objects.create(
            system=system, label='Admin', username='admin', password='pw',
        )
        self._login()
        self.client.get(
            reverse('client_hub:system_credential_detail', kwargs={'pk': cred.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(CredentialAccessLog.objects.count(), 1)
        log = CredentialAccessLog.objects.first()
        self.assertEqual(log.action, 'viewed_by_customer')

    @override_settings(SYSTEM_USER_ID=None)
    def test_credential_detail_has_cache_control_no_store(self):
        prop = Property.objects.filter(customer=self.customer).first()
        system = InstalledSystem.objects.create(
            property=prop, system_type='networking', name='Test System 2',
        )
        cred = SystemCredential.objects.create(
            system=system, label='Admin2', username='admin', password='pw',
        )
        self._login()
        resp = self.client.get(
            reverse('client_hub:system_credential_detail', kwargs={'pk': cred.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Cache-Control'], 'no-store')

    # ── work request ──────────────────────────────────────────────────────────

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_work_request_creates_record_and_sends_emails(self):
        from django.core import mail
        self._login()
        resp = self.client.post(
            reverse('client_hub:work_request_form'),
            {
                'request_types': ['new_install'],
                'description': 'Need new lights',
                'contact_name': 'Carol View',
                'contact_email': 'carol@view.com',
                'contact_phone': '',
                'preferred_contact': 'email',
            },
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertRedirects(
            resp, reverse('client_hub:work_request_success'), fetch_redirect_response=False
        )
        self.assertEqual(WorkRequest.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)

    # ── service plan change ───────────────────────────────────────────────────

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_plan_change_creates_record_and_sends_emails(self):
        from django.core import mail
        prop = Property.objects.filter(customer=self.customer).first()
        prop.stripe_subscription_id = 'sub_test123'
        prop.service_plan_tier = 'tier1'
        prop.save()

        self._login()
        resp = self.client.post(
            reverse('client_hub:service_plan_change', kwargs={'property_pk': prop.pk}),
            {
                'request_type': 'upgrade',
                'requested_tier': 'tier2',
                'reason': '',
            },
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertRedirects(
            resp, reverse('client_hub:service_plan_change_success'), fetch_redirect_response=False
        )
        self.assertEqual(ServicePlanChangeRequest.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)

    # ── account closure ───────────────────────────────────────────────────────

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_account_closure_creates_deletion_request_and_sends_emails(self):
        from django.core import mail
        self._login()
        resp = self.client.post(
            reverse('client_hub:account_closure'),
            {'confirm': True},
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertRedirects(
            resp, reverse('client_hub:account_closure_success'), fetch_redirect_response=False
        )
        self.assertEqual(CredentialDeletionRequest.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)

    # ── profile edit ──────────────────────────────────────────────────────────

    def test_profile_edit_updates_customer_fields(self):
        self._login()
        self.client.post(
            reverse('client_hub:profile_edit'),
            {
                'first_name': 'Caroline',
                'last_name': 'Updated',
                'phone': '555-1234',
                'new_email': '',
            },
            HTTP_HOST=PORTAL_HOST,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, 'Caroline')
        self.assertEqual(self.customer.last_name, 'Updated')
        self.assertEqual(self.customer.phone, '555-1234')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_email_change_sends_confirmation_to_new_and_notification_to_old(self):
        from django.core import mail
        self._login()
        self.client.post(
            reverse('client_hub:profile_edit'),
            {
                'first_name': 'Carol',
                'last_name': 'View',
                'phone': '',
                'new_email': 'carol.new@view.com',
            },
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(len(mail.outbox), 2)
        recipients = {msg.to[0] for msg in mail.outbox}
        self.assertIn('carol.new@view.com', recipients)
        self.assertIn('carol@view.com', recipients)
