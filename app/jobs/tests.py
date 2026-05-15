import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from accounts.models import EmployeeTOTP

from .models import Customer, Job, OnsiteInstall

User = get_user_model()


def _login_staff(client):
    user = User.objects.create_user(
        username="staff@example.com",
        email="staff@example.com",
        password="hunter2!hunter2",
        is_staff=True,
    )
    # Confirm TOTP so the 2FA middleware doesn't redirect every request.
    EmployeeTOTP.objects.create(user=user, confirmed_at=now())
    client.force_login(user)
    return user


def _make_job(status=Job.Status.PAIRING):
    customer = Customer.objects.create(
        first_name="Pat",
        last_name="Smith",
        email="pat@example.com",
    )
    return Job.objects.create(
        invoice_number="DRAFT-ONSITE-TEST",
        customer=customer,
        status=status,
    )


class OnsiteInstallTests(TestCase):
    def test_render_creates_record_and_advances_status(self):
        _login_staff(self.client)
        job = _make_job(status=Job.Status.PAIRING)

        url = reverse("jobs:onsite_install_render", args=[job.invoice_number])
        r = self.client.get(url)

        self.assertEqual(r.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.ONSITE)
        oi = OnsiteInstall.objects.get(job=job)
        self.assertIsNotNone(oi.started_at)
        self.assertIsNone(oi.completed_at)

    def test_save_field_persists_text_and_flag(self):
        _login_staff(self.client)
        job = _make_job()
        self.client.get(reverse("jobs:onsite_install_render", args=[job.invoice_number]))

        save_url = reverse("jobs:onsite_install_save_field", args=[job.invoice_number])

        # Text field.
        r = self.client.post(
            save_url,
            data=json.dumps({"field": "vlan_changes", "value": "VLAN 20 carved out for IoT"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

        # Boolean flag.
        r = self.client.post(
            save_url,
            data=json.dumps({"field": "vlan_configured", "value": True}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)

        oi = OnsiteInstall.objects.get(job=job)
        self.assertEqual(oi.vlan_changes, "VLAN 20 carved out for IoT")
        self.assertTrue(oi.vlan_configured)

    def test_save_field_rejects_unknown_field(self):
        _login_staff(self.client)
        job = _make_job()
        self.client.get(reverse("jobs:onsite_install_render", args=[job.invoice_number]))

        r = self.client.post(
            reverse("jobs:onsite_install_save_field", args=[job.invoice_number]),
            data=json.dumps({"field": "is_staff", "value": True}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_complete_advances_to_walkthrough(self):
        _login_staff(self.client)
        job = _make_job(status=Job.Status.ONSITE)
        self.client.get(reverse("jobs:onsite_install_render", args=[job.invoice_number]))

        r = self.client.post(
            reverse("jobs:onsite_install_complete", args=[job.invoice_number]),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.WALKTHROUGH)
        oi = OnsiteInstall.objects.get(job=job)
        self.assertIsNotNone(oi.completed_at)

    def test_reopen_clears_completed_at(self):
        _login_staff(self.client)
        job = _make_job(status=Job.Status.ONSITE)
        self.client.get(reverse("jobs:onsite_install_render", args=[job.invoice_number]))
        self.client.post(
            reverse("jobs:onsite_install_complete", args=[job.invoice_number]),
            data="{}",
            content_type="application/json",
        )

        r = self.client.post(
            reverse("jobs:onsite_install_reopen", args=[job.invoice_number]),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        oi = OnsiteInstall.objects.get(job=job)
        self.assertIsNone(oi.completed_at)
