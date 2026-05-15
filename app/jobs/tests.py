import json
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from accounts.models import EmployeeTOTP

from .models import (
    BackendInstall,
    CatalogDevice,
    ChecklistItem,
    ChecklistStep,
    ChecklistTemplate,
    Customer,
    Job,
    OnsiteInstall,
    PairingSheet,
    PairingSheetDevice,
    Room,
    RoomDevice,
    SaleLine,
)
from . import views as jobs_views

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


def _make_job(status=Job.Status.PAIRING, invoice_number=None):
    customer = Customer.objects.create(
        first_name="Pat",
        last_name="Smith",
        email="pat@example.com",
    )
    return Job.objects.create(
        invoice_number=invoice_number or f"DRAFT-{uuid.uuid4().hex[:10].upper()}",
        customer=customer,
        status=status,
    )


def _make_water_sensor():
    return CatalogDevice.objects.create(
        device_type=CatalogDevice.DeviceType.SENSOR,
        model_name="Water leak sensor",
        function_slug="water",
    )


def _make_dual_relay():
    return CatalogDevice.objects.create(
        device_type=CatalogDevice.DeviceType.RELAY,
        model_name="MINI-ZB2GS dual relay",
        channels=2,
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


class PairingNamingTests(TestCase):
    def test_dual_relay_generates_light_and_fan_rows(self):
        job = _make_job()
        room = Room.objects.create(job=job, room_type=Room.RoomType.BEDROOM)
        relay = _make_dual_relay()
        rd = RoomDevice.objects.create(room=room, device=relay, quantity=1)
        ps = PairingSheet.objects.create(job=job)

        jobs_views._sync_pairing_rows(ps)
        names = sorted(ps.device_rows.values_list("ha_name", flat=True))
        self.assertEqual(names, ["bedroom_relay_fan", "bedroom_relay_light"])

    def test_dual_relay_with_quantity_two_emits_four_rows(self):
        job = _make_job()
        room = Room.objects.create(job=job, room_type=Room.RoomType.BEDROOM)
        relay = _make_dual_relay()
        RoomDevice.objects.create(room=room, device=relay, quantity=2)
        ps = PairingSheet.objects.create(job=job)

        jobs_views._sync_pairing_rows(ps)
        names = sorted(ps.device_rows.values_list("ha_name", flat=True))
        self.assertEqual(
            names,
            [
                "bedroom_relay_fan_1",
                "bedroom_relay_fan_2",
                "bedroom_relay_light_1",
                "bedroom_relay_light_2",
            ],
        )

    def test_kitchen_water_sensors_use_role_suffixes(self):
        job = _make_job()
        room = Room.objects.create(job=job, room_type=Room.RoomType.KITCHEN)
        sensor = _make_water_sensor()
        RoomDevice.objects.create(room=room, device=sensor, quantity=3)
        ps = PairingSheet.objects.create(job=job)

        jobs_views._sync_pairing_rows(ps)
        names = sorted(ps.device_rows.values_list("ha_name", flat=True))
        self.assertEqual(
            names,
            [
                "kitchen_sensor_water_dishwasher",
                "kitchen_sensor_water_fridge",
                "kitchen_sensor_water_sink",
            ],
        )

    def test_bathroom_water_sensors_use_role_suffixes(self):
        job = _make_job()
        room = Room.objects.create(
            job=job, room_type=Room.RoomType.BATHROOM, custom_name="Master",
        )
        sensor = _make_water_sensor()
        RoomDevice.objects.create(room=room, device=sensor, quantity=2)
        ps = PairingSheet.objects.create(job=job)

        jobs_views._sync_pairing_rows(ps)
        names = sorted(ps.device_rows.values_list("ha_name", flat=True))
        self.assertEqual(
            names,
            [
                "bathroom_primary_sensor_water_sink",
                "bathroom_primary_sensor_water_toilet",
            ],
        )

    def test_single_water_sensor_in_kitchen_still_uses_first_role(self):
        # Even with quantity=1, the role map applies — first sensor gets 'sink'.
        job = _make_job()
        room = Room.objects.create(job=job, room_type=Room.RoomType.KITCHEN)
        sensor = _make_water_sensor()
        RoomDevice.objects.create(room=room, device=sensor, quantity=1)
        ps = PairingSheet.objects.create(job=job)

        jobs_views._sync_pairing_rows(ps)
        names = list(ps.device_rows.values_list("ha_name", flat=True))
        self.assertEqual(names, ["kitchen_sensor_water_sink"])


class RoomNotesTests(TestCase):
    def test_save_notes_persists_text(self):
        _login_staff(self.client)
        job = _make_job(status=Job.Status.PRE_INSTALL)
        room = Room.objects.create(job=job, room_type=Room.RoomType.KITCHEN)

        r = self.client.post(
            reverse("jobs:room_save_notes", args=[job.invoice_number, room.id]),
            data=json.dumps({"notes": "Wall outlet behind fridge is on a 20A breaker."}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        room.refresh_from_db()
        self.assertEqual(room.notes, "Wall outlet behind fridge is on a 20A breaker.")


class CustomSaleLineTests(TestCase):
    def test_create_sale_line_with_custom_row(self):
        job = _make_job(status=Job.Status.SOLD)
        jobs_views._create_sale_lines(job, None, [
            {
                "custom": True,
                "description": "Reused customer-supplied dimmer",
                "unit_cost": Decimal("0.00"),
                "install_charge": Decimal("45.00"),
                "quantity": 1,
                "notes": "labor only",
            },
        ])
        sl = job.sale_lines.get()
        self.assertIsNone(sl.device_id)
        self.assertEqual(sl.custom_description, "Reused customer-supplied dimmer")
        self.assertEqual(sl.install_charge, Decimal("45.00"))
        self.assertEqual(sl.unit_cost, Decimal("0.00"))
        # Total includes the install charge.
        self.assertEqual(jobs_views._sale_total(job), Decimal("45.00"))

    def test_sale_total_includes_install_charge(self):
        job = _make_job(status=Job.Status.SOLD)
        SaleLine.objects.create(
            job=job, device=None, custom_description="Custom mounting bracket",
            quantity=2, unit_cost=Decimal("12.50"), install_charge=Decimal("20.00"),
        )
        # base = 2 * 12.50 = 25.00; install = 20.00; total = 45.00
        self.assertEqual(jobs_views._sale_total(job), Decimal("45.00"))


class BackendInstallCompletionTests(TestCase):
    def _setup_template(self):
        tpl = ChecklistTemplate.current_for("backend-install")
        if tpl is None:
            tpl = ChecklistTemplate.objects.create(
                slug="backend-install", version=1, title="Backend install",
            )
        if not tpl.steps.exists():
            step = ChecklistStep.objects.create(template=tpl, order=1, title="Setup")
            ChecklistItem.objects.create(
                step=step, order=1, kind=ChecklistItem.Kind.CHECK, body_md="Test step",
            )
        return tpl

    def test_render_advances_pre_install_to_backend(self):
        self._setup_template()
        _login_staff(self.client)
        job = _make_job(status=Job.Status.PRE_INSTALL)

        r = self.client.get(reverse("jobs:backend_install_render", args=[job.invoice_number]))
        self.assertEqual(r.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.BACKEND)

    def test_complete_advances_to_pairing(self):
        self._setup_template()
        _login_staff(self.client)
        job = _make_job(status=Job.Status.BACKEND)
        BackendInstall.objects.create(job=job)

        r = self.client.post(
            reverse("jobs:backend_install_complete", args=[job.invoice_number]),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        payload = r.json()
        self.assertEqual(payload["status"], Job.Status.PAIRING)
        self.assertIn("pairing-sheet", payload["pairing_url"])
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.PAIRING)
        bi = BackendInstall.objects.get(job=job)
        self.assertIsNotNone(bi.completed_at)

    def test_reopen_clears_completed_at(self):
        self._setup_template()
        _login_staff(self.client)
        job = _make_job(status=Job.Status.PAIRING)
        BackendInstall.objects.create(job=job, completed_at=now())

        r = self.client.post(
            reverse("jobs:backend_install_reopen", args=[job.invoice_number]),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        bi = BackendInstall.objects.get(job=job)
        self.assertIsNone(bi.completed_at)
        # Status stays at PAIRING — reopen doesn't rewind the job.
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.PAIRING)
