import pyotp
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now

from accounts.models import EmployeeTOTP, RecoveryCode

User = get_user_model()


def _login_url():
    return reverse("accounts:login")


def _verify_url():
    return reverse("accounts:two_factor_verify")


def _setup_url():
    return reverse("accounts:two_factor_setup")


def _recovery_url():
    return reverse("accounts:recovery_login")


def _make_staff(email="rb@example.com", password="hunter2!hunter2", with_totp=True, confirmed=True):
    user = User.objects.create_user(
        username=email, email=email, password=password, is_staff=True,
    )
    totp = None
    if with_totp:
        totp = EmployeeTOTP.objects.create(user=user)
        if confirmed:
            totp.confirmed_at = now()
            totp.save(update_fields=["confirmed_at"])
    return user, totp


def _current_code(totp):
    return pyotp.TOTP(totp.secret).now()


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class LoginFlowTests(TestCase):
    def test_login_with_password_then_totp(self):
        user, totp = _make_staff()

        r = self.client.post(_login_url(), {
            "email": user.email, "password": "hunter2!hunter2",
        })
        self.assertRedirects(r, _verify_url())

        r = self.client.post(_verify_url(), {"code": _current_code(totp)})
        self.assertEqual(r.status_code, 302)
        # User is logged in now.
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_wrong_password_does_not_redirect(self):
        _make_staff()
        r = self.client.post(_login_url(), {
            "email": "rb@example.com", "password": "wrong",
        })
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("pending_user_id", self.client.session)

    def test_wrong_totp_blocks_login(self):
        user, _ = _make_staff()
        self.client.post(_login_url(), {
            "email": user.email, "password": "hunter2!hunter2",
        })
        r = self.client.post(_verify_url(), {"code": "000000"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_totp_code_not_replayable(self):
        user, totp = _make_staff()
        code = _current_code(totp)
        self.client.post(_login_url(), {
            "email": user.email, "password": "hunter2!hunter2",
        })
        self.client.post(_verify_url(), {"code": code})
        self.client.logout()
        # Second use of the same code must fail.
        self.client.post(_login_url(), {
            "email": user.email, "password": "hunter2!hunter2",
        })
        r = self.client.post(_verify_url(), {"code": code})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class EnrolmentTests(TestCase):
    def test_first_login_routes_through_setup_and_generates_recovery_codes(self):
        user, _ = _make_staff(with_totp=False)
        self.client.post(_login_url(), {
            "email": user.email, "password": "hunter2!hunter2",
        })
        # Verify redirects to setup because there's no confirmed TOTP yet.
        r = self.client.get(_verify_url())
        self.assertRedirects(r, _setup_url())

        # GET the setup page so EmployeeTOTP is created.
        self.client.get(_setup_url())
        totp = EmployeeTOTP.objects.get(user=user)
        r = self.client.post(_setup_url(), {"code": _current_code(totp)})
        # First completion redirects to recovery codes.
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:recovery_codes"), r.url)

        # Codes exist (10 by default).
        self.assertEqual(RecoveryCode.objects.filter(user=user).count(), 10)

        # Recovery codes page renders them once.
        r = self.client.get(reverse("accounts:recovery_codes"))
        self.assertContains(r, "Save your recovery codes")


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class RecoveryTests(TestCase):
    def test_recovery_code_logs_user_in_and_is_consumed(self):
        user, _ = _make_staff()
        codes = RecoveryCode.generate_batch(user)
        self.client.post(_login_url(), {
            "email": user.email, "password": "hunter2!hunter2",
        })
        r = self.client.post(_recovery_url(), {"code": codes[0]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

        # Same code can't be reused.
        self.client.logout()
        self.client.post(_login_url(), {
            "email": user.email, "password": "hunter2!hunter2",
        })
        r = self.client.post(_recovery_url(), {"code": codes[0]})
        self.assertEqual(r.status_code, 200)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class MiddlewareTests(TestCase):
    def test_unconfirmed_staff_redirected_to_setup(self):
        user, _ = _make_staff(with_totp=False)
        # Simulate having completed password but not 2FA — bypass by calling
        # login() directly with a "force-login" technique only available to
        # tests:
        self.client.force_login(user, backend="accounts.auth_backends.EmailOrUsernameBackend")
        r = self.client.get(reverse("jobs:home"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/2fa/setup/", r.url)

    def test_confirmed_staff_can_access_dashboard(self):
        user, _ = _make_staff()
        self.client.force_login(user, backend="accounts.auth_backends.EmailOrUsernameBackend")
        r = self.client.get(reverse("jobs:home"))
        self.assertEqual(r.status_code, 200)

    def test_anonymous_user_not_caught_by_middleware(self):
        # Anonymous user gets the jobs view's login_required redirect, not
        # the 2FA enforcement.
        r = self.client.get(reverse("jobs:home"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r.url)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class EmailBackendTests(TestCase):
    def test_authenticate_by_email_case_insensitive(self):
        User.objects.create_user(
            username="ron@example.com", email="ron@example.com",
            password="hunter2!hunter2", is_staff=True,
        )
        r = self.client.post(_login_url(), {
            "email": "RON@example.com", "password": "hunter2!hunter2",
        })
        self.assertEqual(r.status_code, 302)
