"""
Structured pairing sheet rows.

Schema changes:
  - Add CatalogDevice.function_slug (used by the HA-name formula).
  - Replace PairingSheet.devices (JSONField) with PairingSheetDevice rows.
  - Add lock state to PairingSheet (locked/locked_at/locked_by).

Data: seed function_slug for the catalog rows we ship today, based on
model_name / supplier_sku heuristics. Anything we can't classify stays blank
and staff fills it in via admin.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


# (substring_to_match_lower, function_slug). First match wins, so put the
# longer/more specific substrings before generic ones.
FUNCTION_SLUG_RULES = [
    ("water / leak",           "water"),
    ("water sensor",           "water"),
    ("temperature + humidity", "humidity"),
    ("humidity",               "humidity"),
    ("smoke",                  "smoke"),
    (" co ",                   "co"),
    ("vibration",              "vibration"),
    ("tilt",                   "tilt"),
    ("contact sensor",         "door"),
    ("dp-zd001",               "door"),
    ("dp-zd003",               "door"),
    ("perimeter contact",      "door"),
    ("presence",               "presence"),
    ("mmwave",                 "presence"),
    ("fp1e",                   "presence"),
    ("fp2",                    "presence"),
    ("doorbell",               "doorbell"),
    ("ptz",                    "ptz"),
    ("e1 pan",                 "ptz"),
    ("reolink e1",             "ptz"),
    ("scene switch",           "scene"),
    ("snzb-01p",               "scene"),
    ("dimmer",                 "dim"),
    ("mini-zbdim",             "dim"),
    ("vzm31-sn",               "dim"),
    ("inovelli blue",          "dim"),
    ("power monitoring",       "power"),
    ("smart plug",             "plug"),
    ("opener relay",           "opener"),
    ("dry contact",            "opener"),
    # Single relays — general light control.
    ("zbminir2",               "light"),
    ("zbminil2",               "light"),
    # Dual relay covers light + fan in one device; we leave it blank because
    # the row really represents two entities and staff name them manually.
]


def _classify(device) -> str:
    haystack = (
        (device.model_name or "") + " " +
        (device.supplier_sku or "") + " " +
        (device.notes or "")
    ).lower()
    for needle, slug in FUNCTION_SLUG_RULES:
        if needle in haystack:
            return slug
    return ""


def seed_function_slugs(apps, schema_editor):
    CatalogDevice = apps.get_model("jobs", "CatalogDevice")
    for d in CatalogDevice.objects.all():
        slug = _classify(d)
        if slug and d.function_slug != slug:
            d.function_slug = slug
            d.save(update_fields=["function_slug"])


def unseed_function_slugs(apps, schema_editor):
    CatalogDevice = apps.get_model("jobs", "CatalogDevice")
    CatalogDevice.objects.update(function_slug="")


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0018_alter_job_display_invoice_number_alter_job_package"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. CatalogDevice.function_slug
        migrations.AddField(
            model_name="catalogdevice",
            name="function_slug",
            field=models.SlugField(
                blank=True,
                help_text=(
                    "Function token used by the pairing sheet to generate HA entity names "
                    "(e.g. 'door', 'presence', 'light', 'tilt'). The pairing sheet formula "
                    "produces '{room_slug}_{device_kind}_{function_slug}'. Leave blank for "
                    "devices that don't get a name (NUC, UPS, kits)."
                ),
                max_length=40,
            ),
        ),

        # 2. Replace PairingSheet.devices JSONField with lock fields.
        migrations.RemoveField(
            model_name="pairingsheet",
            name="devices",
        ),
        migrations.AddField(
            model_name="pairingsheet",
            name="locked",
            field=models.BooleanField(
                default=False,
                help_text="Locked once pairing is complete. Unlocking is audit-logged after walkthrough.",
            ),
        ),
        migrations.AddField(
            model_name="pairingsheet",
            name="locked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pairingsheet",
            name="locked_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # 3. PairingSheetDevice rows.
        migrations.CreateModel(
            name="PairingSheetDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("instance_index", models.PositiveSmallIntegerField(
                    default=1,
                    help_text="1-based index when a RoomDevice has quantity > 1. Used to disambiguate names.",
                )),
                ("ha_name", models.CharField(
                    blank=True, max_length=120,
                    help_text="Home Assistant / Zigbee2MQTT friendly name. Editable by staff.",
                )),
                ("paired", models.BooleanField(default=False)),
                ("paired_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.CharField(blank=True, max_length=200)),
                ("pairing_sheet", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="device_rows",
                    to="jobs.pairingsheet",
                )),
                ("room_device", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="pairing_rows",
                    to="jobs.roomdevice",
                )),
                ("paired_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["room_device__room__order", "room_device_id", "instance_index"],
            },
        ),
        migrations.AddConstraint(
            model_name="pairingsheetdevice",
            constraint=models.UniqueConstraint(
                fields=("pairing_sheet", "room_device", "instance_index"),
                name="unique_pairing_row_per_instance",
            ),
        ),

        # 4. Seed function_slugs for the existing catalog.
        migrations.RunPython(seed_function_slugs, unseed_function_slugs),
    ]
