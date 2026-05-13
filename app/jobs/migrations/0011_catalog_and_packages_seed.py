"""
Data migration: seed the full DFHA Session 6 (April 2026) catalog and
Connected Home package definitions.

Client prices come from docs/internal/pricing.md (not for client distribution).
Internal BOM costs are stored in the device notes field for reference.

Running this migration twice is safe — get_or_create prevents duplicates.
"""
from decimal import Decimal

from django.db import migrations


# ── Device definitions ────────────────────────────────────────────────────────
# Each tuple: (device_type, model_name, supplier, supplier_sku, default_cost, notes)
# default_cost = client price charged on the sale.

DEVICES = [

    # ── Backend / NUC ──────────────────────────────────────────────────────
    (
        "nuc",
        "Backend setup — N100 NUC · Zigbee dongle · HAOS · full config",
        "Various",
        "",
        Decimal("499.00"),
        "Includes Intel N100 NUC, Sonoff Zigbee Dongle Plus, 32 GB USB drive, "
        "HAOS, Z2M, AdGuard, Tailscale, VLAN, backups, app, ownership doc, "
        "walkthrough, 2–3 hrs labor. BOM hardware: $220–$240 NUC + ~$50–$70 accessories.",
    ),

    # ── UPS ────────────────────────────────────────────────────────────────
    (
        "other",
        "APC Back-UPS 600VA (à la carte)",
        "APC",
        "BX600M1",
        Decimal("149.00"),
        "USB to NUC. Covers NUC + NAS + router + switch. BOM cost: $83.99. "
        "Use bundled price ($100) when included in a Connected Home package.",
    ),

    # ── Room kits — Indoor Comfort ─────────────────────────────────────────
    (
        "kit",
        "Basic room kit — light + presence",
        "Various Zigbee",
        "",
        Decimal("299.00"),
        "ZBMINIR2 or ZBMINIL2 relay + Tuya mmWave presence sensor.",
    ),
    (
        "kit",
        "Living room kit — light + fan + presence",
        "Various Zigbee",
        "",
        Decimal("349.00"),
        "ZBMINIR2 light relay + MINI-ZB2GS fan relay + Tuya mmWave.",
    ),
    (
        "kit",
        "Bedroom kit — relay + presence (single switch, no dimming)",
        "Various Zigbee",
        "",
        Decimal("299.00"),
        "ZBMINIR2 or ZBMINIL2 + Tuya mmWave.",
    ),
    (
        "kit",
        "Bedroom kit — dual relay + fan + presence (no dimming)",
        "Various Zigbee",
        "",
        Decimal("349.00"),
        "MINI-ZB2GS + Tuya mmWave.",
    ),
    (
        "kit",
        "Bedroom kit — dimmer + presence (single switch)",
        "Various Zigbee",
        "",
        Decimal("349.00"),
        "MINI-ZBDIM + Tuya mmWave.",
    ),
    (
        "kit",
        "Bedroom kit — dimmer + fan relay + presence",
        "Various Zigbee",
        "",
        Decimal("399.00"),
        "MINI-ZBDIM + MINI-ZB2GS-L + Tuya mmWave.",
    ),
    (
        "kit",
        "Primary bedroom kit — dimmer + Aqara FP2 60 GHz presence",
        "Various Zigbee / Aqara",
        "",
        Decimal("499.00"),
        "MINI-ZBDIM + Aqara FP2 60 GHz. Premium presence detection.",
    ),
    (
        "kit",
        "Hallway kit — presence-based lighting",
        "Various Zigbee",
        "",
        Decimal("299.00"),
        "ZBMINIR2 or ZBMINIL2 + Tuya mmWave.",
    ),

    # ── Room kits — Indoor Safety ──────────────────────────────────────────
    (
        "kit",
        "Kitchen kit — light + presence + 3× water sensors",
        "Various Zigbee",
        "",
        Decimal("399.00"),
        "ZBMINIR2 + Tuya mmWave + 3× Tuya Zigbee water/leak sensors.",
    ),
    (
        "kit",
        "Bathroom kit — light + fan + presence + humidity + water",
        "Various Zigbee",
        "",
        Decimal("369.00"),
        "2× ZBMINIR2 + Tuya mmWave + humidity sensor + 2× water sensor.",
    ),
    (
        "sensor",
        "Bathroom double vanity add-on — water sensor",
        "Tuya Zigbee",
        "",
        Decimal("15.00"),
        "Additional Tuya Zigbee water sensor at second sink. BOM: ~$10.",
    ),
    (
        "kit",
        "Garage Standard kit — light + tilt + presence",
        "Various Zigbee",
        "",
        Decimal("379.00"),
        "ZBMINIR2 + Tuya Zigbee tilt sensor + Tuya mmWave.",
    ),
    (
        "kit",
        "Garage Premium kit — Standard + camera + opener + contact + vibration",
        "Various Zigbee / Reolink",
        "",
        Decimal("599.00"),
        "Garage Standard + Reolink E1 pan/tilt + dry contact opener relay + "
        "man door contact sensor + 2× vibration sensor. Confirmed Session 6.",
    ),
    (
        "kit",
        "Second garage door add-on — tilt + opener relay + automation",
        "Various Zigbee",
        "",
        Decimal("149.00"),
        "Tilt sensor + dry contact opener relay + second-door automation. Confirmed Session 6.",
    ),
    (
        "kit",
        "Laundry room kit — light + presence + power + vibration + water",
        "Various Zigbee",
        "",
        Decimal("299.00"),
        "ZBMINIR2 + Tuya mmWave + ThirdReality power-monitoring plug + vibration sensor + "
        "water sensor. Confirmed Session 6.",
    ),

    # ── Entry kits ─────────────────────────────────────────────────────────
    (
        "kit",
        "Front porch kit — welcome home + Reolink WiFi doorbell",
        "Various / Reolink",
        "",
        Decimal("449.00"),
        "ZBMINIR2 porch light relay + Reolink Video Doorbell WiFi + Chime V2. "
        "BOM doorbell: $100–$115.",
    ),
    (
        "kit",
        "Front door security kit — approach + entry (lock sold separately)",
        "Various Zigbee",
        "",
        Decimal("349.00"),
        "Tuya mmWave at entry + contact sensor + lock integration. Lock priced separately.",
    ),

    # ── Smart locks ────────────────────────────────────────────────────────
    (
        "lock",
        "Level Bolt smart lock (Bluetooth, invisible interior)",
        "Level",
        "LVL100",
        Decimal("299.00"),
        "Interior only — works through existing deadbolt. ESP32 BLE proxy required "
        "for HA integration. BOM: ~$180.",
    ),
    (
        "lock",
        "Aqara U100 / U200 smart lock (Zigbee, keypad + NFC)",
        "Aqara",
        "U100/U200",
        Decimal("349.00"),
        "Replaces deadbolt. Native Zigbee. BOM: ~$160.",
    ),
    (
        "lock",
        "Aqara U400 smart lock (Zigbee, fingerprint + NFC + keypad)",
        "Aqara",
        "U400",
        Decimal("399.00"),
        "Premium. Replaces deadbolt. Native Zigbee. BOM: ~$230.",
    ),

    # ── Hallway / stairwell kits ───────────────────────────────────────────
    (
        "kit",
        "Two-switch stairwell kit (3-way, presence approach)",
        "Various Zigbee",
        "",
        Decimal("349.00"),
        "Presence sensor replaces 3-way switch complexity.",
    ),
    (
        "kit",
        "Three-switch hallway kit (4-way)",
        "Various Zigbee",
        "",
        Decimal("399.00"),
        "Presence-based. SNZB-01P at secondary locations.",
    ),

    # ── Outdoor / perimeter kits ───────────────────────────────────────────
    (
        "kit",
        "Perimeter lighting kit — up to 3 exterior lights + dusk/dawn + scene",
        "Various Zigbee",
        "",
        Decimal("499.00"),
        "Up to 3× ZBMINIR2 + automations.",
    ),
    (
        "kit",
        "Additional exterior light (beyond 3)",
        "Various Zigbee",
        "",
        Decimal("79.00"),
        "Per additional light beyond the base 3 in the perimeter lighting kit.",
    ),
    (
        "kit",
        "Perimeter sensor kit — up to 3 gate / door contact sensors",
        "Tuya Zigbee",
        "",
        Decimal("299.00"),
        "Up to 3× flush-drilled contact sensors (DP-ZD001 / DP-ZD003).",
    ),
    (
        "sensor",
        "Additional perimeter contact sensor (beyond 3)",
        "Tuya Zigbee",
        "DP-ZD001",
        Decimal("29.00"),
        "Per additional flush-drilled contact sensor beyond the base 3. BOM: $2.25.",
    ),
    (
        "kit",
        "Backyard bundle — lighting + sensors + back door",
        "Various Zigbee",
        "",
        Decimal("649.00"),
        "Combines perimeter lighting kit + perimeter sensor kit.",
    ),
    (
        "kit",
        "Full perimeter kit — backyard + Reolink NVR + 2× PoE cameras",
        "Various / Reolink",
        "",
        Decimal("1349.00"),
        "Reolink RLN8-410 8-port PoE NVR (2 TB) + 2× PoE cameras. BOM NVR: $285.",
    ),

    # ── Contact sensors ────────────────────────────────────────────────────
    (
        "sensor",
        "Contact sensor — flush-drill install (per sensor)",
        "Tuya Zigbee",
        "DP-ZD001",
        Decimal("5.00"),
        "DP-ZD001 or DP-ZD003 ($2.00 BOM) + 3D-printed container ($0.25). "
        "Working price — revisit when wholesale vendor confirmed.",
    ),

    # ── Per-room add-ons ───────────────────────────────────────────────────
    (
        "other",
        "Add-on: 3-way scene switch at second location (SNZB-01P)",
        "Sonoff",
        "SNZB-01P",
        Decimal("49.00"),
        "Wireless scene button. CR2477 5-year battery. BOM: $12.",
    ),
    (
        "relay",
        "Add-on: Dimmer module upgrade (MINI-ZBDIM in-wall)",
        "Various Zigbee",
        "MINI-ZBDIM",
        Decimal("39.00"),
        "In-wall dimmer, neutral required. 200 VA max. Mesh router. BOM: $26.90.",
    ),
    (
        "relay",
        "Add-on: Inovelli Blue Series wallplate dimmer (VZM31-SN)",
        "Inovelli",
        "VZM31-SN",
        Decimal("60.00"),
        "Paddle-style wallplate dimmer. Neutral or no-neutral (Aeotec bypass, ~$10 extra). BOM: $60.",
    ),
    (
        "relay",
        "Add-on: Fan on/off dual relay (MINI-ZB2GS)",
        "Various Zigbee",
        "MINI-ZB2GS",
        Decimal("39.00"),
        "MINI-ZB2GS or MINI-ZB2GS-L. BOM: $17.90–$18.",
    ),
    (
        "sensor",
        "Add-on: Aqara FP1E presence sensor upgrade",
        "Aqara",
        "FP1E",
        Decimal("49.00"),
        "Upgrade over standard Tuya mmWave. BOM: $49.99.",
    ),
    (
        "sensor",
        "Add-on: Aqara FP2 60 GHz presence sensor upgrade",
        "Aqara",
        "FP2",
        Decimal("129.00"),
        "Upgrade over standard Tuya mmWave. WiFi. BOM: $63–$85.",
    ),
    (
        "sensor",
        "Add-on: Second presence sensor — large room (Tuya mmWave)",
        "Tuya Zigbee",
        "",
        Decimal("79.00"),
        "Additional Tuya mmWave for large or open-plan rooms. BOM: $25.",
    ),
    (
        "other",
        "Add-on: Grocy household inventory setup",
        "",
        "",
        Decimal("50.00"),
        "Software config only — no hardware. Grocy running in HA.",
    ),
    (
        "plug",
        "Add-on: Zigbee smart plug — lamp or appliance control",
        "ThirdReality",
        "",
        Decimal("49.00"),
        "ThirdReality Zigbee smart plug (standard on/off). BOM: $12.",
    ),
    (
        "plug",
        "Zigbee smart plug — power monitoring (washing machine cycle)",
        "ThirdReality",
        "",
        Decimal("49.00"),
        "ThirdReality Zigbee smart plug with power monitoring. "
        "Used for washing machine / dryer cycle detection. BOM: $12.",
    ),

    # ── Individual relay devices (for advanced / custom builds) ───────────
    (
        "relay",
        "ZBMINIR2 — single relay, neutral required",
        "Various Zigbee",
        "ZBMINIR2",
        Decimal("15.00"),
        "Standard light on/off. Mesh router. 10 A. BOM: $13–$16.",
    ),
    (
        "relay",
        "ZBMINIL2 — single relay, no neutral",
        "Various Zigbee",
        "ZBMINIL2",
        Decimal("14.00"),
        "Older homes without neutral. End device only. 6 A. BOM: $11–$16.",
    ),
    (
        "relay",
        "MINI-ZB2GS — dual relay, neutral required (light + fan)",
        "Various Zigbee",
        "MINI-ZB2GS",
        Decimal("18.00"),
        "Controls light + fan from same box. Mesh router. 16 A. BOM: $17.90.",
    ),
    (
        "relay",
        "MINI-ZB2GS-L — dual relay, no neutral (light + fan)",
        "Various Zigbee",
        "MINI-ZB2GS-L",
        Decimal("18.00"),
        "No-neutral dual relay. End device. 12 A. BOM: ~$18.",
    ),
    (
        "relay",
        "MINI-ZBDIM — in-wall dimmer, neutral required",
        "Various Zigbee",
        "MINI-ZBDIM",
        Decimal("27.00"),
        "Dimmable LED. 200 VA max. Mesh router. BOM: $26.90.",
    ),
]


# ── Package definitions ───────────────────────────────────────────────────────
# Each entry: (name, description, base_price, monitoring_tier, device_name_list)
# device_name_list: [(model_name_substring, quantity), ...]
# We match by model_name_substring (first device whose model_name contains that string).

PACKAGES = [
    (
        "Connected Home — 1 BR / 1 BA",
        (
            "Includes backend setup, UPS, living room, one bedroom (relay), "
            "bathroom, kitchen, and hallway kits. ~10% bundle discount vs à la carte. "
            "À la carte equivalent: $2,563."
        ),
        Decimal("2249.00"),
        0,  # monitoring_tier: sold separately via ServiceSubscription
        [
            ("Backend setup", 1),
            ("APC Back-UPS 600VA (à la carte)", 1),
            ("Living room kit", 1),
            ("Bedroom kit — relay + presence (single switch", 1),
            ("Bathroom kit", 1),
            ("Kitchen kit", 1),
            ("Hallway kit", 1),
        ],
    ),
    (
        "Connected Home — 2 BR / 2 BA",
        (
            "Includes backend setup, UPS, living room, two bedrooms (relay), "
            "two bathrooms, kitchen, and hallway kits. ~10% bundle discount vs à la carte. "
            "À la carte equivalent: $3,281."
        ),
        Decimal("2899.00"),
        0,
        [
            ("Backend setup", 1),
            ("APC Back-UPS 600VA (à la carte)", 1),
            ("Living room kit", 1),
            ("Bedroom kit — relay + presence (single switch", 2),
            ("Bathroom kit", 2),
            ("Kitchen kit", 1),
            ("Hallway kit", 1),
        ],
    ),
    (
        "Connected Home — 3 BR / 2 BA",
        (
            "Includes backend setup, UPS, living room, two standard bedrooms (relay), "
            "one primary bedroom (dimmer + Aqara FP2), two bathrooms, kitchen, and hallway "
            "kits. ~10% bundle discount vs à la carte. À la carte equivalent: $3,630."
        ),
        Decimal("3199.00"),
        0,
        [
            ("Backend setup", 1),
            ("APC Back-UPS 600VA (à la carte)", 1),
            ("Living room kit", 1),
            ("Bedroom kit — relay + presence (single switch", 2),
            ("Primary bedroom kit", 1),
            ("Bathroom kit", 2),
            ("Kitchen kit", 1),
            ("Hallway kit", 1),
        ],
    ),
]


def seed_catalog(apps, schema_editor):
    CatalogDevice = apps.get_model("jobs", "CatalogDevice")
    Package = apps.get_model("jobs", "Package")
    PackageDevice = apps.get_model("jobs", "PackageDevice")

    created_devices = {}

    for (dtype, model_name, supplier, sku, cost, notes) in DEVICES:
        obj, _ = CatalogDevice.objects.get_or_create(
            model_name=model_name,
            defaults=dict(
                device_type=dtype,
                supplier=supplier,
                supplier_sku=sku,
                default_cost=cost,
                notes=notes,
                active=True,
            ),
        )
        created_devices[model_name] = obj

    def _find_device(substring):
        for name, device in created_devices.items():
            if substring in name:
                return device
        # Fallback to DB lookup in case of re-run where device already existed.
        return CatalogDevice.objects.filter(model_name__icontains=substring, active=True).first()

    for (pkg_name, description, base_price, monitoring_tier, device_list) in PACKAGES:
        pkg, created = Package.objects.get_or_create(
            name=pkg_name,
            defaults=dict(
                description=description,
                base_price=base_price,
                monitoring_tier=monitoring_tier,
                active=True,
            ),
        )
        if created:
            for (device_substr, qty) in device_list:
                device = _find_device(device_substr)
                if device:
                    PackageDevice.objects.get_or_create(
                        package=pkg,
                        device=device,
                        defaults={"quantity": qty},
                    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0010_invoice_number_generation"),
    ]

    operations = [
        # Update Django's migration state with the new DeviceType choices
        # (no DB change needed — choices are only enforced at the Python layer).
        migrations.AlterField(
            model_name="catalogdevice",
            name="device_type",
            field=__import__("django.db.models", fromlist=["CharField"]).CharField(
                choices=[
                    ("nuc", "NUC / Server"),
                    ("switch", "Network switch"),
                    ("ap", "Access point"),
                    ("relay", "Smart relay"),
                    ("plug", "Smart plug"),
                    ("sensor", "Sensor"),
                    ("camera", "Camera"),
                    ("lock", "Smart lock"),
                    ("thermostat", "Thermostat"),
                    ("hub", "Hub / bridge"),
                    ("kit", "Room / install kit"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(seed_catalog, noop),
    ]
