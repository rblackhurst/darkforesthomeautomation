"""
Seed the "pre-install" v1 ChecklistTemplate.

Four steps covering the discovery call and internal prep a DFHA installer
runs between a sale closing and the physical install day.  All content is
editable in admin afterwards without a code deploy.
"""
from django.db import migrations


STEPS = [
    {
        "title": "Package & scope confirmation",
        "items": [
            ("check",   "Package scope verbally confirmed with customer", "", "", ""),
            ("capture", "", "package_summary", "Package description",
             "e.g. Standard HA package — NUC + 6× Zigbee sensors + doorbell camera"),
            ("check",   "Pricing and payment terms confirmed", "", "", ""),
            ("check",   "Invoice sent to customer", "", "", ""),
        ],
    },
    {
        "title": "Network & infrastructure baseline",
        "items": [
            ("capture", "", "isp", "Internet service provider", "e.g. Comcast, AT&T Fiber"),
            ("capture", "", "router", "Current router brand + model", "e.g. ASUS RT-AX86U"),
            ("check",   "DHCP range will allow a static reservation for NUC", "", "", ""),
            ("check",   "Ethernet connectivity to NUC location confirmed (or cable run planned)", "", "", ""),
            ("check",   "Customer has or will get a managed switch if VLAN setup is in scope", "", "", ""),
        ],
    },
    {
        "title": "On-site logistics",
        "items": [
            ("capture", "", "nuc_location",
             "NUC placement location", "e.g. office closet, utility room near router"),
            ("check",   "Power outlet at NUC location confirmed", "", "", ""),
            ("capture", "", "install_contact",
             "On-site contact (if different from account holder)",
             "Name + best phone number"),
            ("check",   "Customer (or household member) will be home for full install (~4–6 hours)", "", "", ""),
            ("check",   "Parking and building-access details noted", "", "", ""),
        ],
    },
    {
        "title": "Internal prep",
        "items": [
            ("check",   "Pick sheet generated from package details", "", "", ""),
            ("check",   "All devices ordered or confirmed in stock", "", "", ""),
            ("check",   "Customer GitHub account creation scheduled for backend-install step", "", "", ""),
            ("check",   "Customer Tailscale account creation scheduled for backend-install step", "", "", ""),
        ],
    },
]


def seed_pre_install(apps, schema_editor):
    ChecklistTemplate = apps.get_model("jobs", "ChecklistTemplate")
    ChecklistStep = apps.get_model("jobs", "ChecklistStep")
    ChecklistItem = apps.get_model("jobs", "ChecklistItem")

    template = ChecklistTemplate.objects.create(
        slug="pre-install",
        version=1,
        title="Pre-install checklist",
        changelog="Initial seed: discovery call + internal-prep steps.",
    )

    for step_order, step_data in enumerate(STEPS, start=1):
        step = ChecklistStep.objects.create(
            template=template,
            order=step_order,
            title=step_data["title"],
        )
        for item_order, (kind, body, key, label, placeholder) in enumerate(
            step_data["items"], start=1
        ):
            ChecklistItem.objects.create(
                step=step,
                order=item_order,
                kind=kind,
                body_md=body,
                capture_key=key,
                capture_label=label,
                capture_placeholder=placeholder,
            )


def unseed_pre_install(apps, schema_editor):
    ChecklistTemplate = apps.get_model("jobs", "ChecklistTemplate")
    ChecklistTemplate.objects.filter(slug="pre-install", version=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0006_catalog_and_pre_install"),
    ]
    operations = [
        migrations.RunPython(seed_pre_install, unseed_pre_install),
    ]
