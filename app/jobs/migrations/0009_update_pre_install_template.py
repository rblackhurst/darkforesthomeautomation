"""
Replace the "Internal prep" step in the pre-install v1 template with a
single content block directing staff to the Internal Prep page.  This
avoids duplicating the device-list / GitHub-account work that now has
its own dedicated view.
"""
from django.db import migrations


def update_pre_install_template(apps, schema_editor):
    ChecklistStep = apps.get_model("jobs", "ChecklistStep")
    ChecklistItem = apps.get_model("jobs", "ChecklistItem")
    ChecklistTemplate = apps.get_model("jobs", "ChecklistTemplate")

    try:
        template = ChecklistTemplate.objects.get(slug="pre-install", version=1)
    except ChecklistTemplate.DoesNotExist:
        return  # template was never seeded (e.g. test env)

    # Remove the old "Internal prep" step (step 4) entirely.
    ChecklistStep.objects.filter(template=template, title="Internal prep").delete()

    # Add a new step 4: a single content block pointing staff to the
    # dedicated Internal Prep page.
    step = ChecklistStep.objects.create(
        template=template,
        order=4,
        title="Internal prep",
        intro_md=(
            "Complete the Internal Prep page before the install date. "
            "It tracks pick-list generation, stock confirmation, and the "
            "customer GitHub account — all pre-populated from this sale."
        ),
    )
    ChecklistItem.objects.create(
        step=step,
        order=1,
        kind="check",
        body_md="Internal prep complete — pick sheet generated, all devices confirmed in stock, GitHub account created",
    )


def revert_pre_install_template(apps, schema_editor):
    # Restore the original four internal-prep items.
    ChecklistStep = apps.get_model("jobs", "ChecklistStep")
    ChecklistItem = apps.get_model("jobs", "ChecklistItem")
    ChecklistTemplate = apps.get_model("jobs", "ChecklistTemplate")

    try:
        template = ChecklistTemplate.objects.get(slug="pre-install", version=1)
    except ChecklistTemplate.DoesNotExist:
        return

    ChecklistStep.objects.filter(template=template, order=4).delete()

    step = ChecklistStep.objects.create(
        template=template, order=4, title="Internal prep",
    )
    for i, body in enumerate([
        "Pick sheet generated from package details",
        "All devices ordered or confirmed in stock",
        "Customer GitHub account creation scheduled for backend-install step",
        "Customer Tailscale account creation scheduled for backend-install step",
    ], start=1):
        ChecklistItem.objects.create(step=step, order=i, kind="check", body_md=body)


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0008_packages_salelines_internalprep_rooms"),
    ]
    operations = [
        migrations.RunPython(
            update_pre_install_template,
            revert_pre_install_template,
        ),
    ]
