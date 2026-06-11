from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now

_SIMPLE_STORAGE = {
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}

from accounts.models import EmployeeTOTP
from client_credentials.models import (
    CredentialAccessLog,
    Device,
    DeviceCredential,
    InstalledSystem,
    SystemCredential,
)
from jobs.models import Customer

User = get_user_model()


def make_customer():
    return Customer.objects.create(first_name='Jane', last_name='Smith', email='jane@example.com')


def make_system(customer):
    return InstalledSystem.objects.create(
        customer=customer,
        system_type=InstalledSystem.SystemType.NETWORKING,
        name='Main Network',
    )


def make_device(system):
    return Device.objects.create(system=system, name='Front Door Camera', device_type='IP Camera')


def make_staff_user(username='staff1'):
    user = User.objects.create_user(username=username, password='testpass', is_staff=True)
    EmployeeTOTP.objects.create(user=user, confirmed_at=now())
    return user


def make_regular_user(username='user1'):
    return User.objects.create_user(username=username, password='testpass', is_staff=False)


@override_settings(STORAGES=_SIMPLE_STORAGE)
class SystemCredentialDetailViewTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.system = make_system(self.customer)
        self.credential = SystemCredential.objects.create(
            system=self.system,
            label='Router Admin',
            password='secretpass',
        )
        self.url = reverse('client_credentials:system_credential_detail', args=[self.credential.pk])

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/accounts/login/?next={self.url}', fetch_redirect_response=False)

    def test_non_staff_gets_403(self):
        user = make_regular_user()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_staff_gets_200(self):
        user = make_staff_user()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_staff_access_creates_log_entry(self):
        user = make_staff_user()
        self.client.force_login(user)
        self.client.get(self.url)
        self.assertEqual(CredentialAccessLog.objects.filter(action='viewed').count(), 1)

    def test_log_entry_has_correct_content_type_and_object_id(self):
        user = make_staff_user()
        self.client.force_login(user)
        self.client.get(self.url)
        log = CredentialAccessLog.objects.get(action='viewed')
        ct = ContentType.objects.get_for_model(SystemCredential)
        self.assertEqual(log.content_type, ct)
        self.assertEqual(log.object_id, self.credential.pk)

    def test_response_contains_credential_label(self):
        user = make_staff_user()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertContains(response, 'Router Admin')

    def test_response_has_no_cache_header(self):
        user = make_staff_user()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_nonexistent_pk_returns_404(self):
        user = make_staff_user()
        self.client.force_login(user)
        url = reverse('client_credentials:system_credential_detail', args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


@override_settings(STORAGES=_SIMPLE_STORAGE)
class DeviceCredentialDetailViewTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.system = make_system(self.customer)
        self.device = make_device(self.system)
        self.credential = DeviceCredential.objects.create(
            device=self.device,
            label='Admin Password',
            credential_type=DeviceCredential.CredentialType.PASSWORD,
            value='devicepass',
        )
        self.url = reverse('client_credentials:device_credential_detail', args=[self.credential.pk])

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/accounts/login/?next={self.url}', fetch_redirect_response=False)

    def test_non_staff_gets_403(self):
        user = make_regular_user()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_staff_gets_200(self):
        user = make_staff_user()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_staff_access_creates_log_entry(self):
        user = make_staff_user()
        self.client.force_login(user)
        self.client.get(self.url)
        self.assertEqual(CredentialAccessLog.objects.filter(action='viewed').count(), 1)

    def test_log_entry_has_correct_content_type_and_object_id(self):
        user = make_staff_user()
        self.client.force_login(user)
        self.client.get(self.url)
        log = CredentialAccessLog.objects.get(action='viewed')
        ct = ContentType.objects.get_for_model(DeviceCredential)
        self.assertEqual(log.content_type, ct)
        self.assertEqual(log.object_id, self.credential.pk)

    def test_response_contains_credential_label(self):
        user = make_staff_user()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertContains(response, 'Admin Password')

    def test_response_has_no_cache_header(self):
        user = make_staff_user()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_nonexistent_pk_returns_404(self):
        user = make_staff_user()
        self.client.force_login(user)
        url = reverse('client_credentials:device_credential_detail', args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
