"""
Add room notes, dual-relay channel count, and off-catalog custom sale lines.

Schema:
  - Room.notes (TextField)
  - CatalogDevice.channels (PositiveSmallIntegerField, default=1)
  - SaleLine.device now nullable (for custom off-catalog lines)
  - SaleLine.custom_description (CharField)
  - SaleLine.install_charge (DecimalField)

Data:
  - Set channels=2 on dual-relay catalog rows so the pairing sheet generates two
    named entities per unit (light + fan by default).
"""

from django.db import migrations, models


DUAL_RELAY_NAME_SUBSTRINGS = [
    "dual relay",
    "mini-zb2gs",
]


def seed_dual_relay_channels(apps, schema_editor):
    # Only set channels=2 on actual relay rows. Kit rows that happen to mention
    # "dual relay" in their description are bundles, not paired devices.
    CatalogDevice = apps.get_model("jobs", "CatalogDevice")
    for d in CatalogDevice.objects.exclude(device_type="kit"):
        name = (d.model_name or "").lower()
        if any(s in name for s in DUAL_RELAY_NAME_SUBSTRINGS):
            if d.channels != 2:
                d.channels = 2
                d.save(update_fields=["channels"])


def unseed_dual_relay_channels(apps, schema_editor):
    CatalogDevice = apps.get_model("jobs", "CatalogDevice")
    CatalogDevice.objects.update(channels=1)


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0020_onsite_install_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="room",
            name="notes",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Walkthrough notes for this room — anything the customer mentioned, "
                    "access quirks, wiring concerns, or device-placement reminders."
                ),
            ),
        ),
        migrations.AddField(
            model_name="catalogdevice",
            name="channels",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text=(
                    "How many independently-named HA entities this device produces. "
                    "Dual relays (e.g. MINI-ZB2GS light + fan) set this to 2, so the "
                    "pairing sheet generates two named rows per unit."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="saleline",
            name="device",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="sale_lines",
                to="jobs.catalogdevice",
                help_text=(
                    "Catalog device. Leave blank for a custom off-catalog line — "
                    "describe it in custom_description and set unit_cost manually."
                ),
            ),
        ),
        migrations.AddField(
            model_name="saleline",
            name="custom_description",
            field=models.CharField(
                blank=True,
                max_length=200,
                help_text=(
                    "Description shown in pick sheets / pricing when this line is "
                    "off-catalog (device is blank)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="saleline",
            name="install_charge",
            field=models.DecimalField(
                blank=True,
                null=True,
                max_digits=10,
                decimal_places=2,
                help_text=(
                    "Optional labor / installation charge for this line on top of "
                    "unit_cost × quantity. Used for off-catalog custom items."
                ),
            ),
        ),
        migrations.RunPython(seed_dual_relay_channels, unseed_dual_relay_channels),
    ]
