from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0019_pairing_sheet_structured"),
    ]

    operations = [
        migrations.AddField(
            model_name="onsiteinstall",
            name="vlan_configured",
            field=models.BooleanField(
                default=False,
                help_text="VLAN / DHCP reservations applied on the customer's router.",
            ),
        ),
        migrations.AddField(
            model_name="onsiteinstall",
            name="tailscale_active",
            field=models.BooleanField(
                default=False,
                help_text="Tailscale signed in on the customer's NUC and reachable from a phone.",
            ),
        ),
        migrations.AddField(
            model_name="onsiteinstall",
            name="remote_access_verified",
            field=models.BooleanField(
                default=False,
                help_text="Verified the customer can reach Home Assistant from outside their LAN.",
            ),
        ),
    ]
