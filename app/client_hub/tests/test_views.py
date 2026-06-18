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

    # ── credential download ───────────────────────────────────────────────────

    @override_settings(SYSTEM_USER_ID=None)
    def test_download_credentials_returns_json_file(self):
        prop = Property.objects.filter(customer=self.customer).first()
        system = InstalledSystem.objects.create(
            property=prop, system_type='networking', name='Network',
        )
        SystemCredential.objects.create(
            system=system, label='Router', username='admin', password='secret',
        )
        self._login()
        resp = self.client.get(
            reverse('client_hub:download_credentials', kwargs={'pk': prop.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        self.assertIn('attachment', resp['Content-Disposition'])
        self.assertIn('.json', resp['Content-Disposition'])
        self.assertEqual(resp['Cache-Control'], 'no-store')

    @override_settings(SYSTEM_USER_ID=None)
    def test_download_credentials_contains_decrypted_values(self):
        prop = Property.objects.filter(customer=self.customer).first()
        system = InstalledSystem.objects.create(
            property=prop, system_type='access', name='Access',
        )
        SystemCredential.objects.create(
            system=system, label='Hub', username='owner', password='topsecret',
        )
        self._login()
        resp = self.client.get(
            reverse('client_hub:download_credentials', kwargs={'pk': prop.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        import json as _json
        data = _json.loads(resp.content)
        cred = data['systems'][0]['credentials'][0]
        self.assertEqual(cred['label'], 'Hub')
        self.assertEqual(cred['username'], 'owner')
        self.assertEqual(cred['password'], 'topsecret')

    @override_settings(SYSTEM_USER_ID=None)
    def test_download_credentials_logs_each_credential_access(self):
        prop = Property.objects.filter(customer=self.customer).first()
        system = InstalledSystem.objects.create(
            property=prop, system_type='lighting', name='Lights',
        )
        SystemCredential.objects.create(
            system=system, label='App', username='u', password='pw',
        )
        self._login()
        self.client.get(
            reverse('client_hub:download_credentials', kwargs={'pk': prop.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        from client_credentials.models import CredentialAccessLog
        self.assertEqual(CredentialAccessLog.objects.count(), 1)
        self.assertEqual(CredentialAccessLog.objects.first().action, 'viewed_by_customer')

    def test_download_credentials_other_customers_property_returns_404(self):
        other = Customer.objects.create(
            first_name='X', last_name='Y', email='xy@view.com'
        )
        other_prop = Property.objects.filter(customer=other).first()
        self._login()
        resp = self.client.get(
            reverse('client_hub:download_credentials', kwargs={'pk': other_prop.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 404)

    def test_download_credentials_unauthenticated_redirects(self):
        prop = Property.objects.filter(customer=self.customer).first()
        resp = self._get('client_hub:download_credentials', kwargs={'pk': prop.pk})
        self.assertRedirects(
            resp, reverse('client_hub:login'), fetch_redirect_response=False
        )

    # ── account closure passes properties ─────────────────────────────────────

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_account_closure_form_includes_properties_in_context(self):
        self._login()
        resp = self.client.get(
            reverse('client_hub:account_closure'),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('properties', resp.context)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_account_closure_success_includes_properties_in_context(self):
        self._login()
        resp = self.client.get(
            reverse('client_hub:account_closure_success'),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('properties', resp.context)

    # ── install document ──────────────────────────────────────────────────────

    def test_install_document_unauthenticated_redirects_to_login(self):
        prop = Property.objects.filter(customer=self.customer).first()
        resp = self._get('client_hub:install_document', kwargs={'pk': prop.pk})
        self.assertRedirects(
            resp, reverse('client_hub:login'), fetch_redirect_response=False
        )

    def test_install_document_other_customers_property_returns_404(self):
        other = Customer.objects.create(
            first_name='Other', last_name='Doc', email='other.doc@view.com'
        )
        other_prop = Property.objects.filter(customer=other).first()
        self._login()
        resp = self.client.get(
            reverse('client_hub:install_document', kwargs={'pk': other_prop.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 404)

    def test_install_document_own_property_returns_200(self):
        prop = Property.objects.filter(customer=self.customer).first()
        self._login()
        resp = self.client.get(
            reverse('client_hub:install_document', kwargs={'pk': prop.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 200)

    def test_install_document_shows_systems_credentials_and_devices(self):
        prop = Property.objects.filter(customer=self.customer).first()
        system = InstalledSystem.objects.create(
            property=prop,
            system_type='networking',
            name='Home Network',
            manufacturer='Ubiquiti',
        )
        cred = SystemCredential.objects.create(
            system=system,
            label='Router Admin',
            username='admin',
            portal_url='http://192.168.1.1',
            password='secret123',
        )
        device = Device.objects.create(
            system=system,
            name='Dream Machine Pro',
            manufacturer='Ubiquiti',
            model_number='UDM-Pro',
            serial_number='SN123456',
            mac_address='AA:BB:CC:DD:EE:FF',
            ip_address='192.168.1.1',
            firmware_version='3.2.1',
            location='Network closet',
        )
        dcred = DeviceCredential.objects.create(
            device=device,
            label='Admin PIN',
            credential_type='pin',
            value='9876',
        )
        self._login()
        resp = self.client.get(
            reverse('client_hub:install_document', kwargs={'pk': prop.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Home Network')
        self.assertContains(resp, 'Router Admin')
        self.assertContains(resp, 'admin')
        self.assertContains(resp, 'http://192.168.1.1')
        self.assertContains(resp, 'Dream Machine Pro')
        self.assertContains(resp, 'SN123456')
        self.assertContains(resp, 'AA:BB:CC:DD:EE:FF')
        self.assertContains(resp, '192.168.1.1')
        self.assertContains(resp, '3.2.1')
        self.assertContains(resp, 'Network closet')
        self.assertContains(resp, 'Admin PIN')
        # Credential values must NOT appear on the index page
        self.assertNotContains(resp, 'secret123')
        self.assertNotContains(resp, '9876')

    def test_install_document_hides_invisible_credentials_and_devices(self):
        prop = Property.objects.filter(customer=self.customer).first()
        system = InstalledSystem.objects.create(
            property=prop,
            system_type='lighting',
            name='Visible System',
        )
        SystemCredential.objects.create(
            system=system,
            label='Hidden Cred',
            username='hide_me',
            password='pw',
            is_visible=False,
        )
        Device.objects.create(
            system=system,
            name='Hidden Device',
            is_visible=False,
        )
        self._login()
        resp = self.client.get(
            reverse('client_hub:install_document', kwargs={'pk': prop.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Hidden Cred')
        self.assertNotContains(resp, 'hide_me')
        self.assertNotContains(resp, 'Hidden Device')

    def test_install_document_links_to_credential_reveal_views(self):
        prop = Property.objects.filter(customer=self.customer).first()
        system = InstalledSystem.objects.create(
            property=prop,
            system_type='access',
            name='Access Control',
        )
        cred = SystemCredential.objects.create(
            system=system, label='Hub Login', username='owner', password='pw',
        )
        device = Device.objects.create(system=system, name='Smart Lock')
        dcred = DeviceCredential.objects.create(
            device=device, label='Lock Code', credential_type='pin', value='1234',
        )
        self._login()
        resp = self.client.get(
            reverse('client_hub:install_document', kwargs={'pk': prop.pk}),
            HTTP_HOST=PORTAL_HOST,
        )
        self.assertContains(
            resp,
            reverse('client_hub:system_credential_detail', kwargs={'pk': cred.pk}),
        )
        self.assertContains(
            resp,
            reverse('client_hub:device_credential_detail', kwargs={'pk': dcred.pk}),
        )

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
