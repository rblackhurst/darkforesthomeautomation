"""
Three data changes:
  1. Remove Step 4 "Internal prep" from the pre-install checklist template —
     it lives on the dedicated Internal Prep page.
  2. Extend Package.default_rooms to include per-room device assignments so
     the walkthrough arrives pre-populated.
  3. Refresh the package_summary capture logic is handled in the view; no
     schema change needed here.
"""
from django.db import migrations


PACKAGE_ROOMS = {
    "Connected Home — 1 BR / 1 BA": [
        {"room_type": "living_room", "devices": [{"model_name_contains": "Living room kit"}]},
        {"room_type": "kitchen",     "devices": [{"model_name_contains": "Kitchen kit"}]},
        {"room_type": "hallway",     "devices": [{"model_name_contains": "Hallway kit"}]},
        {"room_type": "bedroom",     "devices": [{"model_name_contains": "Bedroom kit — relay"}]},
        {"room_type": "bathroom",    "devices": [{"model_name_contains": "Bathroom kit"}]},
    ],
    "Connected Home — 2 BR / 2 BA": [
        {"room_type": "living_room", "devices": [{"model_name_contains": "Living room kit"}]},
        {"room_type": "kitchen",     "devices": [{"model_name_contains": "Kitchen kit"}]},
        {"room_type": "hallway",     "devices": [{"model_name_contains": "Hallway kit"}]},
        {"room_type": "bedroom",     "devices": [{"model_name_contains": "Bedroom kit — relay"}]},
        {"room_type": "bedroom",     "devices": [{"model_name_contains": "Bedroom kit — relay"}]},
        {"room_type": "bathroom",    "devices": [{"model_name_contains": "Bathroom kit"}]},
        {"room_type": "bathroom",    "devices": [{"model_name_contains": "Bathroom kit"}]},
    ],
    "Connected Home — 3 BR / 2 BA": [
        {"room_type": "living_room", "devices": [{"model_name_contains": "Living room kit"}]},
        {"room_type": "kitchen",     "devices": [{"model_name_contains": "Kitchen kit"}]},
        {"room_type": "hallway",     "devices": [{"model_name_contains": "Hallway kit"}]},
        {"room_type": "bedroom", "custom_name": "Primary",
         "devices": [{"model_name_contains": "Primary bedroom kit"}]},
        {"room_type": "bedroom",     "devices": [{"model_name_contains": "Bedroom kit — relay"}]},
        {"room_type": "bedroom",     "devices": [{"model_name_contains": "Bedroom kit — relay"}]},
        {"room_type": "bathroom",    "devices": [{"model_name_contains": "Bathroom kit"}]},
        {"room_type": "bathroom",    "devices": [{"model_name_contains": "Bathroom kit"}]},
    ],
}


def remove_internal_prep_step(apps, schema_editor):
    ChecklistStep = apps.get_model("jobs", "ChecklistStep")
    ChecklistStep.objects.filter(
        title="Internal prep",
        template__slug="pre-install",
    ).delete()


def update_package_room_devices(apps, schema_editor):
    Package = apps.get_model("jobs", "Package")
    for name, rooms in PACKAGE_ROOMS.items():
        Package.objects.filter(name=name).update(default_rooms=rooms)


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0014_room_from_package"),
    ]

    operations = [
        migrations.RunPython(remove_internal_prep_step, migrations.RunPython.noop),
        migrations.RunPython(update_package_room_devices, migrations.RunPython.noop),
    ]
