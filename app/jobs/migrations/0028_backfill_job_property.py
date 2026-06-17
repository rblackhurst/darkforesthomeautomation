from django.db import migrations


def backfill_job_property(apps, schema_editor):
    Job = apps.get_model('jobs', 'Job')
    Property = apps.get_model('jobs', 'Property')
    for job in Job.objects.filter(property__isnull=True).select_related('customer'):
        prop = Property.objects.create(customer=job.customer)
        job.property = prop
        job.save(update_fields=['property'])


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0027_backendinstall_final_checks'),
    ]

    operations = [
        migrations.RunPython(backfill_job_property, migrations.RunPython.noop),
    ]
