import django.db.models.deletion
from django.db import migrations, models


def seed_dhcp_reservation(apps, schema_editor):
    """Set needs_dhcp_reservation=True for device types that always need a static IP."""
    CatalogDevice = apps.get_model("jobs", "CatalogDevice")
    dhcp_types = {"nuc", "switch", "ap", "hub", "camera"}
    CatalogDevice.objects.filter(device_type__in=dhcp_types).update(needs_dhcp_reservation=True)


def migrate_tailscale_to_walkthrough(apps, schema_editor):
    """Move any tailscale_account values from OnsiteInstall to WalkthroughSignoff."""
    OnsiteInstall = apps.get_model("jobs", "OnsiteInstall")
    WalkthroughSignoff = apps.get_model("jobs", "WalkthroughSignoff")
    for oi in OnsiteInstall.objects.exclude(tailscale_account=""):
        try:
            ws = WalkthroughSignoff.objects.get(job=oi.job)
            if not ws.tailscale_account:
                ws.tailscale_account = oi.tailscale_account
                ws.save(update_fields=["tailscale_account"])
        except WalkthroughSignoff.DoesNotExist:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0025_add_property_model"),
    ]

    operations = [
        # 1. Add needs_dhcp_reservation to CatalogDevice
        migrations.AddField(
            model_name="catalogdevice",
            name="needs_dhcp_reservation",
            field=models.BooleanField(
                default=False,
                help_text="True if this device requires a static DHCP reservation (NUC, switch, AP, hub, camera).",
            ),
        ),
        migrations.RunPython(seed_dhcp_reservation, migrations.RunPython.noop),

        # 2. Add tailscale_account to WalkthroughSignoff (before removing from OnsiteInstall)
        migrations.AddField(
            model_name="walkthroughsignoff",
            name="tailscale_account",
            field=models.CharField(
                blank=True,
                max_length=200,
                help_text="Customer's Tailscale account email, set up at the start of the walkthrough.",
            ),
        ),
        migrations.RunPython(migrate_tailscale_to_walkthrough, migrations.RunPython.noop),

        # 3. Modify OnsiteInstall: remove tailscale_account, add lan_subnet + standard_checks
        migrations.RemoveField(model_name="onsiteinstall", name="tailscale_account"),
        migrations.AddField(
            model_name="onsiteinstall",
            name="lan_subnet",
            field=models.CharField(
                blank=True,
                max_length=50,
                help_text="Base network for DHCP plan (first 3 octets), e.g. '192.168.10'.",
            ),
        ),
        migrations.AddField(
            model_name="onsiteinstall",
            name="standard_checks",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="State of standard onsite checklist items keyed by slug.",
            ),
        ),

        # 4. Create OnsiteDeviceCheck
        migrations.CreateModel(
            name="OnsiteDeviceCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "onsite_install",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="device_checks",
                        to="jobs.onsiteinstall",
                    ),
                ),
                (
                    "pairing_row",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="onsite_checks",
                        to="jobs.pairingsheetdevice",
                    ),
                ),
                ("installed", models.BooleanField(default=False)),
                ("installed_at", models.DateTimeField(blank=True, null=True)),
                ("tested", models.BooleanField(default=False)),
                ("tested_at", models.DateTimeField(blank=True, null=True)),
                (
                    "ip_address",
                    models.CharField(
                        blank=True,
                        max_length=50,
                        help_text="Static IP assigned (only for devices requiring a DHCP reservation).",
                    ),
                ),
                ("notes", models.CharField(blank=True, max_length=200)),
            ],
            options={
                "ordering": [
                    "pairing_row__room_device__room__order",
                    "pairing_row__room_device_id",
                    "pairing_row__instance_index",
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="onsitedevicecheck",
            constraint=models.UniqueConstraint(
                fields=["onsite_install", "pairing_row"],
                name="unique_onsite_device_check",
            ),
        ),
    ]
