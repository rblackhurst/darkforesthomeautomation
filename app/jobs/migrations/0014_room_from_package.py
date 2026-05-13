from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0013_package_rooms_and_invoice_sent"),
    ]

    operations = [
        migrations.AddField(
            model_name="room",
            name="from_package",
            field=models.BooleanField(
                default=False,
                help_text="True if this room was auto-created from the package default_rooms list. "
                          "Allows re-applying a package without losing manually-added rooms.",
            ),
        ),
    ]
