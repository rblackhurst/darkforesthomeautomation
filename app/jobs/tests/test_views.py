from accounts.models import EmployeeTOTP
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from jobs.models import Customer, Job, Property
from stripe_integration.models import InternalAlert

User = get_user_model()

APP_HOST = 'app.darkforesthomeautomation.com'


@override_settings(
    ALLOWED_HOSTS=[APP_HOST, 'testserver', 'localhost'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class PaymentAlertViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='staff', password='pass', email='staff@dfha.internal',
            is_staff=True,
        )
        # Satisfy the Require2FAMiddleware — staff must have a confirmed TOTP.
        EmployeeTOTP.objects.create(user=self.staff, confirmed_at=timezone.now())
        self.customer = Customer.objects.create(
            first_name='Alice', last_name='Alert', email='alice@alert.com'
        )
        self.job = Job.objects.create(
            invoice_number='ALERT-001',
            customer=self.customer,
            status='walkthrough',
        )

    def _login(self):
        self.client.login(username='staff', password='pass')

    def _get(self, url_name, **kwargs):
        return self.client.get(
            reverse(url_name, **kwargs),
            HTTP_HOST=APP_HOST,
        )

    def _post(self, url_name, data, kwargs=None):
        return self.client.post(
            reverse(url_name, **(kwargs or {})),
            data,
            HTTP_HOST=APP_HOST,
        )

    # ── auth ──────────────────────────────────────────────────────────────────

    def test_payment_alerts_requires_login(self):
        resp = self._get('jobs:payment_alerts')
        self.assertNotEqual(resp.status_code, 200)

    # ── list page ─────────────────────────────────────────────────────────────

    def test_payment_alerts_empty_state(self):
        self._login()
        resp = self._get('jobs:payment_alerts')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['unreviewed_count'], 0)

    def test_payment_alerts_shows_unreviewed_alerts(self):
        InternalAlert.objects.create(
            job=self.job,
            alert_type='payment_failed',
            stripe_event_id='evt_test_001',
            message='Payment failed for deposit invoice.',
        )
        self._login()
        resp = self._get('jobs:payment_alerts')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['unreviewed_count'], 1)
        self.assertContains(resp, 'Payment failed for deposit invoice.')

    def test_payment_alerts_reviewed_alert_has_zero_unreviewed_count(self):
        alert = InternalAlert.objects.create(
            job=self.job,
            alert_type='payment_failed',
            stripe_event_id='evt_test_002',
            message='Already reviewed.',
            reviewed=True,
            reviewed_by=self.staff,
            reviewed_at=timezone.now(),
        )
        self._login()
        resp = self._get('jobs:payment_alerts')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['unreviewed_count'], 0)

    # ── mark reviewed ─────────────────────────────────────────────────────────

    def test_mark_reviewed_sets_reviewed_flag(self):
        alert = InternalAlert.objects.create(
            job=self.job,
            alert_type='payment_failed',
            stripe_event_id='evt_test_003',
            message='Test alert.',
        )
        self.assertFalse(alert.reviewed)
        self._login()
        self.client.post(
            reverse('jobs:alert_mark_reviewed', kwargs={'alert_id': alert.pk}),
            data={'next': reverse('jobs:payment_alerts')},
            HTTP_HOST=APP_HOST,
        )
        alert.refresh_from_db()
        self.assertTrue(alert.reviewed)
        self.assertEqual(alert.reviewed_by, self.staff)

    def test_mark_reviewed_redirects_to_next(self):
        alert = InternalAlert.objects.create(
            job=self.job,
            alert_type='payment_failed',
            stripe_event_id='evt_test_004',
            message='Test alert 2.',
        )
        self._login()
        resp = self.client.post(
            reverse('jobs:alert_mark_reviewed', kwargs={'alert_id': alert.pk}),
            data={'next': reverse('jobs:payment_alerts')},
            HTTP_HOST=APP_HOST,
        )
        self.assertRedirects(
            resp, reverse('jobs:payment_alerts'), fetch_redirect_response=False
        )

    # ── job_list alert count ──────────────────────────────────────────────────

    def test_job_list_passes_unreviewed_alert_count(self):
        InternalAlert.objects.create(
            job=self.job,
            alert_type='payment_failed',
            stripe_event_id='evt_test_005',
            message='Unreviewed.',
        )
        self._login()
        resp = self._get('jobs:home')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['unreviewed_alert_count'], 1)

    def test_job_list_alert_count_zero_with_no_alerts(self):
        self._login()
        resp = self._get('jobs:home')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['unreviewed_alert_count'], 0)
