"""Bootstrap a TOTP device for a staff user.

Run once per user on the server before they log in for the first time after
2FA is rolled out:

    python manage.py dfha_enroll_2fa <username>

Prints an `otpauth://` URI and an ASCII-art QR code that an authenticator app
(Aegis, 1Password, Google Authenticator, etc.) can scan. After scanning, the
user's next admin login will require both their password and a 6-digit code
from the authenticator.

Re-running for a user who already has a confirmed device aborts with a clear
error so we don't silently invalidate working enrolments. Pass --replace to
delete existing devices first (only after the user confirms they've lost
access to the prior one).
"""

import io

import qrcode
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice


class Command(BaseCommand):
    help = "Enrol a staff user in TOTP-based two-factor authentication."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete any existing TOTP devices for this user first.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"No user named {username!r}.") from exc

        if not user.is_staff:
            raise CommandError(
                f"User {username!r} is not staff — 2FA is only for staff accounts."
            )

        existing = TOTPDevice.objects.filter(user=user)
        if existing.exists():
            if not options["replace"]:
                raise CommandError(
                    f"User {username!r} already has {existing.count()} TOTP "
                    "device(s). Re-run with --replace to wipe and re-enrol."
                )
            existing.delete()
            self.stdout.write(self.style.WARNING("Removed existing TOTP device(s)."))

        device = TOTPDevice.objects.create(
            user=user,
            name="default",
            confirmed=True,
        )

        uri = device.config_url
        qr = qrcode.QRCode(border=1)
        qr.add_data(uri)
        qr.make(fit=True)
        buf = io.StringIO()
        qr.print_ascii(out=buf, invert=True)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Enrolled {username} in 2FA."))
        self.stdout.write("")
        self.stdout.write("Scan this QR code with an authenticator app:")
        self.stdout.write("")
        self.stdout.write(buf.getvalue())
        self.stdout.write("Or paste this URI manually:")
        self.stdout.write(f"  {uri}")
        self.stdout.write("")
        self.stdout.write(
            "Next admin login will require the password + a 6-digit code "
            "from the authenticator."
        )
