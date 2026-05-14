from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0011_catalog_and_packages_seed"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="service_plan_tier",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, "None / not selected"),
                    (1, "Basic ($29/mo)"),
                    (2, "Standard ($49/mo)"),
                    (3, "Premium ($79/mo)"),
                ],
                default=0,
                help_text="Uptime service plan the customer signed up for "
                          "(uptime checks, updates, battery kits, on-site visits). "
                          "Encodes as the M digit in the invoice number.",
            ),
        ),
    ]
