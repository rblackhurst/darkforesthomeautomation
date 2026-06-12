from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from client_credentials.models import (
    CredentialAccessLog,
    CredentialDeletionRequest,
    Device,
    DeviceCredential,
    InstalledSystem,
    SystemCredential,
)
from jobs.models import Customer, Job, Property

User = get_user_model()


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_customer(**kwargs):
    defaults = dict(first_name='Jane', last_name='Smith', email='jane@example.com')
    defaults.update(kwargs)
    return Customer.objects.create(**defaults)


def make_job(customer, **kwargs):
    defaults = dict(invoice_number='TEST-001', final_paid=False)
    defaults.update(kwargs)
    return Job.objects.create(customer=customer, **defaults)


def make_system(customer, **kwargs):
    defaults = dict(system_type=InstalledSystem.SystemType.NETWORKING, name='Main Network')
    defaults.update(kwargs)
    prop = customer.properties.first()
    return InstalledSystem.objects.create(property=prop, **defaults)


def make_device(system, **kwargs):
    defaults = dict(name='Front Door Camera', device_type='IP Camera')
    defaults.update(kwargs)
    return Device.objects.create(system=system, **defaults)


def make_user(**kwargs):
    defaults = dict(username='tech1', password='testpass123')
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


# ── Model creation ────────────────────────────────────────────────────────────

class InstalledSystemCreationTests(TestCase):
    def test_creates_with_required_fields(self):
        customer = make_customer()
        system = make_system(customer)
        self.assertEqual(system.property.customer, customer)
        self.assertEqual(system.system_type, InstalledSystem.SystemType.NETWORKING)
        self.assertEqual(system.name, 'Main Network')
        self.assertTrue(system.is_visible)

    def test_creates_with_job(self):
        customer = make_customer()
        job = make_job(customer)
        system = make_system(customer, job=job)
        self.assertEqual(system.job, job)

    def test_str(self):
        customer = make_customer()
        system = make_system(customer)
        self.assertIn('Networking', str(system))
        self.assertIn('Main Network', str(system))


class SystemCredentialCreationTests(TestCase):
    def test_creates_with_required_fields(self):
        customer = make_customer()
        system = make_system(customer)
        cred = SystemCredential.objects.create(
            system=system,
            label='Router Admin',
            username='admin',
            password='secret123',
        )
        self.assertEqual(cred.system, system)
        self.assertEqual(cred.label, 'Router Admin')
        self.assertEqual(cred.password, 'secret123')
        self.assertTrue(cred.is_visible)

    def test_str(self):
        customer = make_customer()
        system = make_system(customer)
        cred = SystemCredential.objects.create(system=system, label='Router Admin')
        self.assertIn('Router Admin', str(cred))


class DeviceCreationTests(TestCase):
    def test_creates_with_required_fields(self):
        customer = make_customer()
        system = make_system(customer)
        device = make_device(system)
        self.assertEqual(device.system, system)
        self.assertEqual(device.name, 'Front Door Camera')
        self.assertTrue(device.is_visible)

    def test_optional_fields(self):
        customer = make_customer()
        system = make_system(customer)
        device = Device.objects.create(
            system=system,
            name='NUC',
            ip_address='192.168.1.10',
            mac_address='AA:BB:CC:DD:EE:FF',
            serial_number='SN12345',
            location='Server Closet',
        )
        self.assertEqual(device.ip_address, '192.168.1.10')
        self.assertEqual(device.location, 'Server Closet')

    def test_str(self):
        customer = make_customer()
        system = make_system(customer)
        device = make_device(system)
        self.assertIn('Front Door Camera', str(device))


class DeviceCredentialCreationTests(TestCase):
    def test_creates_with_required_fields(self):
        customer = make_customer()
        system = make_system(customer)
        device = make_device(system)
        cred = DeviceCredential.objects.create(
            device=device,
            label='Admin Password',
            credential_type=DeviceCredential.CredentialType.PASSWORD,
            value='supersecret',
        )
        self.assertEqual(cred.device, device)
        self.assertEqual(cred.value, 'supersecret')
        self.assertTrue(cred.is_visible)

    def test_str(self):
        customer = make_customer()
        system = make_system(customer)
        device = make_device(system)
        cred = DeviceCredential.objects.create(
            device=device,
            label='Admin Password',
            credential_type=DeviceCredential.CredentialType.PASSWORD,
            value='pw',
        )
        self.assertIn('Admin Password', str(cred))


class CredentialAccessLogCreationTests(TestCase):
    def test_creates_with_valid_data(self):
        user = make_user()
        customer = make_customer()
        system = make_system(customer)
        cred = SystemCredential.objects.create(system=system, label='Test')
        ct = ContentType.objects.get_for_model(SystemCredential)

        log = CredentialAccessLog.objects.create(
            accessed_by=user,
            content_type=ct,
            object_id=cred.pk,
            action='viewed',
        )
        self.assertEqual(log.accessed_by, user)
        self.assertEqual(log.action, 'viewed')
        self.assertEqual(log.credential, cred)

    def test_str(self):
        user = make_user()
        customer = make_customer()
        system = make_system(customer)
        cred = SystemCredential.objects.create(system=system, label='Test')
        ct = ContentType.objects.get_for_model(SystemCredential)
        log = CredentialAccessLog.objects.create(
            accessed_by=user, content_type=ct, object_id=cred.pk, action='viewed',
        )
        self.assertIn('viewed', str(log))


class CredentialDeletionRequestCreationTests(TestCase):
    def test_creates_with_required_fields(self):
        customer = make_customer()
        req = CredentialDeletionRequest.objects.create(
            customer=customer,
            scope_notes='Delete all camera credentials',
        )
        self.assertEqual(req.customer, customer)
        self.assertEqual(req.status, CredentialDeletionRequest.Status.PENDING)
        self.assertFalse(req.re_onboarding_fee_disclosed)

    def test_str(self):
        customer = make_customer()
        req = CredentialDeletionRequest.objects.create(
            customer=customer,
            scope_notes='All credentials',
        )
        self.assertIn('Pending', str(req))


# ── CredentialAccessLog immutability ─────────────────────────────────────────

class CredentialAccessLogImmutabilityTests(TestCase):
    def _make_log(self):
        user = make_user()
        customer = make_customer()
        system = make_system(customer)
        cred = SystemCredential.objects.create(system=system, label='Test')
        ct = ContentType.objects.get_for_model(SystemCredential)
        return CredentialAccessLog.objects.create(
            accessed_by=user, content_type=ct, object_id=cred.pk, action='viewed',
        )

    def test_update_raises(self):
        log = self._make_log()
        log.action = 'modified'
        with self.assertRaises(ValueError):
            log.save()

    def test_delete_raises(self):
        log = self._make_log()
        with self.assertRaises(ValueError):
            log.delete()


# ── CredentialDeletionRequest status transitions ──────────────────────────────

class CredentialDeletionRequestStatusTests(TestCase):
    def setUp(self):
        self.customer = make_customer()

    def _make_req(self, status):
        return CredentialDeletionRequest.objects.create(
            customer=self.customer,
            scope_notes='All',
            status=status,
        )

    def test_all_valid_statuses_accepted(self):
        for status, _ in CredentialDeletionRequest.Status.choices:
            req = self._make_req(status)
            req.refresh_from_db()
            self.assertEqual(req.status, status)


# ── Encrypted fields stored as ciphertext ────────────────────────────────────

class EncryptedFieldStorageTests(TestCase):
    def _raw(self, table, column, pk):
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {column} FROM {table} WHERE id = %s", [pk])
            return cursor.fetchone()[0]

    def test_system_credential_password_not_plaintext(self):
        customer = make_customer()
        system = make_system(customer)
        cred = SystemCredential.objects.create(
            system=system, label='Test', password='plaintextpassword'
        )
        raw = self._raw('client_credentials_systemcredential', 'password', cred.pk)
        self.assertNotEqual(raw, 'plaintextpassword')
        self.assertIsNotNone(raw)

    def test_system_credential_api_key_not_plaintext(self):
        customer = make_customer()
        system = make_system(customer)
        cred = SystemCredential.objects.create(
            system=system, label='Test', api_key='myapikey12345'
        )
        raw = self._raw('client_credentials_systemcredential', 'api_key', cred.pk)
        self.assertNotEqual(raw, 'myapikey12345')
        self.assertIsNotNone(raw)

    def test_device_credential_value_not_plaintext(self):
        customer = make_customer()
        system = make_system(customer)
        device = make_device(system)
        cred = DeviceCredential.objects.create(
            device=device,
            label='Admin',
            credential_type=DeviceCredential.CredentialType.PASSWORD,
            value='secretvalue999',
        )
        raw = self._raw('client_credentials_devicecredential', 'value', cred.pk)
        self.assertNotEqual(raw, 'secretvalue999')
        self.assertIsNotNone(raw)

    def test_decrypted_value_matches_original(self):
        customer = make_customer()
        system = make_system(customer)
        cred = SystemCredential.objects.create(
            system=system, label='Test', password='roundtrip'
        )
        fetched = SystemCredential.objects.get(pk=cred.pk)
        self.assertEqual(fetched.password, 'roundtrip')


# ── Soft delete ───────────────────────────────────────────────────────────────

class SoftDeleteTests(TestCase):
    def test_is_visible_false_does_not_delete(self):
        customer = make_customer()
        system = make_system(customer)
        system.is_visible = False
        system.save()
        self.assertTrue(InstalledSystem.objects.filter(pk=system.pk).exists())

    def test_device_soft_delete(self):
        customer = make_customer()
        system = make_system(customer)
        device = make_device(system)
        device.is_visible = False
        device.save()
        self.assertTrue(Device.objects.filter(pk=device.pk).exists())


# ── ForeignKey protection ─────────────────────────────────────────────────────

class ForeignKeyProtectionTests(TestCase):
    def test_deleting_customer_with_installed_system_raises(self):
        customer = make_customer()
        make_system(customer)
        with self.assertRaises(ProtectedError):
            customer.delete()

    def test_deleting_customer_with_deletion_request_raises(self):
        customer = make_customer()
        CredentialDeletionRequest.objects.create(
            customer=customer, scope_notes='All credentials',
        )
        with self.assertRaises(ProtectedError):
            customer.delete()
