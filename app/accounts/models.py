import secrets

import pyotp
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models


def _new_totp_secret():
    return pyotp.random_base32()


class EmployeeTOTP(models.Model):
    """One TOTP enrolment per user.

    `confirmed_at` only flips once the user has typed a valid code from the
    authenticator app — until then the secret exists but doesn't gate login,
    so an interrupted setup can be retried without locking anyone out.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="totp",
    )
    secret = models.CharField(max_length=64, default=_new_totp_secret)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_counter = models.BigIntegerField(
        default=0,
        help_text="Highest TOTP counter accepted for this user — blocks code "
                  "re-use within its 30-second window.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        state = "confirmed" if self.confirmed_at else "pending"
        return f"TOTP({self.user_id}, {state})"

    @property
    def is_confirmed(self):
        return self.confirmed_at is not None

    def provisioning_uri(self, issuer="DFHA"):
        label = self.user.get_username()
        return pyotp.TOTP(self.secret).provisioning_uri(name=label, issuer_name=issuer)

    def verify(self, code, valid_window=1):
        """Return True if `code` is valid for the current step.

        `valid_window=1` accepts the previous, current, and next 30s code to
        tolerate a small clock skew. Successful verification advances
        `last_used_counter` so the same code can't be replayed.
        """
        import time

        if not code:
            return False
        code = code.strip()
        if not code.isdigit():
            return False
        totp = pyotp.TOTP(self.secret)
        step = totp.interval
        base_counter = int(time.time()) // step
        for offset in range(-valid_window, valid_window + 1):
            counter = base_counter + offset
            if counter <= self.last_used_counter:
                continue
            if totp.at(counter * step) == code:
                self.last_used_counter = counter
                self.save(update_fields=["last_used_counter", "updated_at"])
                return True
        return False


class RecoveryCode(models.Model):
    """One-time backup codes shown once at enrolment.

    Stored hashed (Django's password hasher) so a DB read doesn't leak them.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recovery_codes",
    )
    code_hash = models.CharField(max_length=255)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    @classmethod
    def generate_batch(cls, user, count=10):
        cls.objects.filter(user=user).delete()
        plain = []
        for _ in range(count):
            code = "-".join(
                secrets.token_hex(2) for _ in range(2)
            )  # e.g. "a1b2-c3d4"
            cls.objects.create(user=user, code_hash=make_password(code))
            plain.append(code)
        return plain

    @classmethod
    def consume(cls, user, code):
        if not code:
            return False
        normalized = code.strip().lower().replace(" ", "")
        for rc in cls.objects.filter(user=user, used_at__isnull=True):
            if check_password(normalized, rc.code_hash):
                from django.utils.timezone import now as _now
                rc.used_at = _now()
                rc.save(update_fields=["used_at"])
                return True
        return False
