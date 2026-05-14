"""
Three changes:
  1. Package.default_rooms — JSON list of rooms to auto-create when a package is sold.
  2. PreInstallChecklist.invoice_sent / invoice_sent_at — tracks whether the
     payment quote has been confirmed sent to the customer (moved out of the
     template step loop and into the Finalize section of the UI).
  3. Data: remove the old "Invoice sent to customer" ChecklistItem from Step 1
     of the pre-install template (it is now a dedicated field).
  4. Data: seed default_rooms for the three standard packages.
"""
import django.db.models.deletion
from django.db import migrations, models


PACKAGE_ROOMS = {
    "Connected Home — 1 BR / 1 BA": [
        {"room_type": "living_room"},
        {"room_type": "kitchen"},
        {"room_type": "hallway"},
        {"room_type": "bedroom"},
        {"room_type": "bathroom"},
    ],
    "Connected Home — 2 BR / 2 BA": [
        {"room_type": "living_room"},
        {"room_type": "kitchen"},
        {"room_type": "hallway"},
        {"room_type": "bedroom"},
        {"room_type": "bedroom"},
        {"room_type": "bathroom"},
        {"room_type": "bathroom"},
    ],
    "Connected Home — 3 BR / 2 BA": [
        {"room_type": "living_room"},
        {"room_type": "kitchen"},
        {"room_type": "hallway"},
        {"room_type": "bedroom", "custom_name": "Primary"},
        {"room_type": "bedroom"},
        {"room_type": "bedroom"},
        {"room_type": "bathroom"},
        {"room_type": "bathroom"},
    ],
}


def remove_invoice_sent_item(apps, schema_editor):
    ChecklistItem = apps.get_model("jobs", "ChecklistItem")
    ChecklistItem.objects.filter(
        body_md="Invoice sent to customer",
        step__template__slug="pre-install",
    ).delete()


def seed_package_rooms(apps, schema_editor):
    Package = apps.get_model("jobs", "Package")
    for name, rooms in PACKAGE_ROOMS.items():
        Package.objects.filter(name=name).update(default_rooms=rooms)


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0012_job_service_plan_tier"),
    ]

    operations = [
        migrations.AddField(
            model_name="preinstallchecklist",
            name="invoice_sent",
            field=models.BooleanField(
                default=False,
                help_text="Checked once the payment quote / invoice has been confirmed sent to the customer.",
            ),
        ),
        migrations.AddField(
            model_name="preinstallchecklist",
            name="invoice_sent_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="package",
            name="default_rooms",
            field=models.JSONField(
                null=True,
                blank=True,
                help_text='Rooms to auto-create when this package is selected at sale time. '
                          'List of objects: {"room_type": "bedroom", "custom_name": "Primary"}. '
                          'custom_name is optional.',
            ),
        ),
        migrations.RunPython(remove_invoice_sent_item, migrations.RunPython.noop),
        migrations.RunPython(seed_package_rooms, migrations.RunPython.noop),
    ]
