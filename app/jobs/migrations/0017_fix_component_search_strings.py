"""
Fix ambiguous model_name_contains strings in Package.default_rooms:
  - "FP2 60"      → "FP2 60 GHz presence sensor"  (was matching the kit entry)
  - "MINI-ZBDIM"  → "MINI-ZBDIM —"               (was matching the add-on variant)
"""
from django.db import migrations


def forward(apps, schema_editor):
    Package = apps.get_model("jobs", "Package")

    def fix_rooms(rooms):
        changed = False
        for room in rooms:
            for dev in room.get("devices", []):
                s = dev.get("model_name_contains", "")
                if s == "FP2 60":
                    dev["model_name_contains"] = "FP2 60 GHz presence sensor"
                    changed = True
                elif s == "MINI-ZBDIM":
                    dev["model_name_contains"] = "MINI-ZBDIM —"
                    changed = True
        return changed

    for pkg in Package.objects.filter(active=True):
        if pkg.default_rooms and fix_rooms(pkg.default_rooms):
            pkg.save(update_fields=["default_rooms"])


def backward(apps, schema_editor):
    Package = apps.get_model("jobs", "Package")

    def revert_rooms(rooms):
        changed = False
        for room in rooms:
            for dev in room.get("devices", []):
                s = dev.get("model_name_contains", "")
                if s == "FP2 60 GHz presence sensor":
                    dev["model_name_contains"] = "FP2 60"
                    changed = True
                elif s == "MINI-ZBDIM —":
                    dev["model_name_contains"] = "MINI-ZBDIM"
                    changed = True
        return changed

    for pkg in Package.objects.filter(active=True):
        if pkg.default_rooms and revert_rooms(pkg.default_rooms):
            pkg.save(update_fields=["default_rooms"])


class Migration(migrations.Migration):
    dependencies = [("jobs", "0016_expand_kits_to_individual_devices")]
    operations = [migrations.RunPython(forward, backward)]
