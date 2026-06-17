from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0026_onsite_install_rework"),
    ]

    operations = [
        migrations.AddField(
            model_name="backendinstall",
            name="final_checks",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="State of final-verification checklist items keyed by slug.",
            ),
        ),
    ]
