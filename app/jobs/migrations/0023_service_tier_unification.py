from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Pre-Phase 3 cleanup:
    - Convert Job.service_plan_tier from PositiveSmallIntegerField to CharField with TextChoices.
    - Remove Job.plan_tier (superseded by service_plan_tier).
    - Remove Package.monitoring_tier (no longer used now that invoice numbers omit the tier digit).

    No data migration needed: all existing records are test data.
    """

    dependencies = [
        ('jobs', '0022_drop_servicesubscription'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='service_plan_tier',
            field=models.CharField(
                blank=True,
                choices=[
                    ('none', 'No Service Plan'),
                    ('tier1', 'Basic'),
                    ('tier2', 'Standard'),
                    ('tier3', 'Premium'),
                ],
                default='none',
                help_text='Uptime service plan the customer signed up for (uptime checks, updates, battery kits, on-site visits).',
                max_length=10,
            ),
        ),
        migrations.RemoveField(
            model_name='job',
            name='plan_tier',
        ),
        migrations.RemoveField(
            model_name='package',
            name='monitoring_tier',
        ),
    ]
