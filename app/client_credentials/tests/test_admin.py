from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from accounts.models import EmployeeTOTP
from client_credentials.admin import CredentialDeletionRequestAdmin
from client_credentials.models import CredentialDeletionRequest, InstalledSystem
from jobs.admin import CustomerAdmin
from jobs.models import Customer

User = get_user_model()


def make_customer(email='jane@example.com'):
    return Customer.objects.create(first_name='Jane', last_name='Smith', email=email)


def make_staff_user(username='staff1'):
    user = User.objects.create_user(username=username, password='testpass', is_staff=True, is_superuser=True)
    EmployeeTOTP.objects.create(user=user, confirmed_at=now())
    return user


class CustomerAdminCredentialTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.admin = CustomerAdmin(Customer, AdminSite())

    def test_pending_deletion_col_shows_warning_when_pending(self):
        CredentialDeletionRequest.objects.create(
            customer=self.customer,
            scope_notes='Delete all',
            status='pending',
        )
        result = str(self.admin.pending_deletion_col(self.customer))
        self.assertIn('Pending deletion request', result)

    def test_pending_deletion_col_returns_dash_when_no_pending(self):
        result = self.admin.pending_deletion_col(self.customer)
        self.assertEqual(result, '—')

    def test_pending_deletion_col_returns_dash_when_only_resolved(self):
        CredentialDeletionRequest.objects.create(
            customer=self.customer,
            scope_notes='Delete all',
            status='executed',
        )
        result = self.admin.pending_deletion_col(self.customer)
        self.assertEqual(result, '—')

    def test_system_count_col_returns_correct_count(self):
        InstalledSystem.objects.create(
            customer=self.customer,
            system_type=InstalledSystem.SystemType.NETWORKING,
            name='Test System',
        )
        result = str(self.admin.system_count_col(self.customer))
        self.assertIn('1', result)

    def test_system_count_col_returns_no_systems_when_empty(self):
        result = self.admin.system_count_col(self.customer)
        self.assertEqual(result, 'No systems')

    def test_system_count_col_excludes_hidden_systems(self):
        InstalledSystem.objects.create(
            customer=self.customer,
            system_type=InstalledSystem.SystemType.NETWORKING,
            name='Hidden System',
            is_visible=False,
        )
        result = self.admin.system_count_col(self.customer)
        self.assertEqual(result, 'No systems')


class CredentialDeletionRequestAdminTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.admin = CredentialDeletionRequestAdmin(CredentialDeletionRequest, AdminSite())

    def _make_req(self, status):
        return CredentialDeletionRequest.objects.create(
            customer=self.customer,
            scope_notes='All',
            status=status,
        )

    def test_status_col_pending_has_red_styling(self):
        req = self._make_req('pending')
        result = str(self.admin.status_col(req))
        self.assertIn('c62828', result)
        self.assertIn('Pending', result)

    def test_status_col_executed_has_green_styling(self):
        req = self._make_req('executed')
        result = str(self.admin.status_col(req))
        self.assertIn('2e7d32', result)
        self.assertIn('Executed', result)

    def test_status_col_staff_contacted_has_orange_styling(self):
        req = self._make_req('staff_contacted')
        result = str(self.admin.status_col(req))
        self.assertIn('e65100', result)

    def test_status_col_cancelled_has_grey_styling(self):
        req = self._make_req('cancelled')
        result = str(self.admin.status_col(req))
        self.assertIn('666', result)
