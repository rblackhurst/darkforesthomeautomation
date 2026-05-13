from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0009_update_pre_install_template"),
    ]

    operations = [
        # Package: add monitoring_tier
        migrations.AddField(
            model_name="package",
            name="monitoring_tier",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Monitoring tier digit encoded in the invoice number (0–9). "
                          "0 = no monitoring, 1 = basic, 2 = standard, 3 = premium, etc.",
            ),
        ),

        # SaleLine: add from_package flag
        migrations.AddField(
            model_name="saleline",
            name="from_package",
            field=models.BooleanField(
                default=False,
                help_text="True if this line was pre-filled from the selected package.",
            ),
        ),

        # Job: package FK
        migrations.AddField(
            model_name="job",
            name="package",
            field=models.ForeignKey(
                blank=True,
                help_text="Package selected at sale time — used for the monitoring-tier digit in the invoice number.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="jobs",
                to="jobs.package",
            ),
        ),

        # Job: custom integrations / automations
        migrations.AddField(
            model_name="job",
            name="custom_integrations",
            field=models.TextField(
                blank=True,
                help_text="Existing devices the customer wants integrated (e.g. smart locks, cameras). "
                          "Note: most cloud-only devices (Google Nest, etc.) cannot be integrated.",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="custom_automations",
            field=models.TextField(
                blank=True,
                help_text="Custom automation requests beyond the standard package.",
            ),
        ),

        # Job: display invoice number (the formatted customer-facing code)
        migrations.AddField(
            model_name="job",
            name="display_invoice_number",
            field=models.CharField(
                blank=True,
                help_text="System-generated customer-facing invoice code (YYMMDD + tier + rooms + adhoc + seq). "
                          "Set when the pre-install walkthrough is finalized.",
                max_length=30,
                null=True,
                unique=True,
            ),
        ),

        # Job: finalization + payment fields
        migrations.AddField(
            model_name="job",
            name="finalized_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the sale was finalized and the invoice number was generated.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="payment_override",
            field=models.BooleanField(
                default=False,
                help_text="Skip the automatic payment email — handle payment manually.",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="payment_override_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Custom total override for testing / reduced-price installs.",
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="payment_received",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="job",
            name="payment_received_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
