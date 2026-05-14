"""
Expand room-kit catalog entries into individual component devices.

  1. Add two new CatalogDevice entries:
       - Aqara SJCGQ11LM — water / leak sensor  (sensor)
       - Aqara WSDCGQ11LM — temperature + humidity sensor  (sensor)

  2. Rewrite Package.default_rooms for all three Connected Home packages
     so each room lists individual component devices instead of one kit entry.

  3. Expand any existing RoomDevice rows that reference a kit catalog entry
     into their individual component rows (safe for DRAFT jobs in the wild;
     already-finalized jobs can re-do rooms via the swap/add UI).
"""

from django.db import migrations


# ── Individual-component device specs per kit model_name ─────────────────────
# key  = substring that uniquely matches the kit's model_name (case-insensitive)
# value = list of model_name_contains strings for the replacement components;
#         a string may repeat to create multiple RoomDevice rows of the same device.

KIT_EXPANSION = {
    "Living room kit": [
        "ZBMINIR2",        # single relay — light
        "MINI-ZB2GS —",    # dual relay — fan (neutral)
        "FP1E",            # presence sensor
    ],
    "Kitchen kit": [
        "ZBMINIR2",
        "FP1E",
        "water / leak",    # sensor under sink
        "water / leak",    # sensor near dishwasher
        "water / leak",    # sensor near refrigerator
    ],
    "Hallway kit": [
        "ZBMINIR2",
        "FP1E",
    ],
    "Bathroom kit": [
        "ZBMINIR2",
        "MINI-ZB2GS —",
        "FP1E",
        "temperature + humidity",
        "water / leak",
    ],
    # Bedroom variants — matched in order of specificity (longest key first)
    "Primary bedroom kit": [
        "MINI-ZBDIM",
        "FP2 60",          # Aqara FP2 60 GHz
    ],
    "Bedroom kit — dimmer + fan": [
        "MINI-ZBDIM",
        "MINI-ZB2GS —",
        "FP1E",
    ],
    "Bedroom kit — dimmer + presence": [
        "MINI-ZBDIM",
        "FP1E",
    ],
    "Bedroom kit — dual relay": [
        "MINI-ZB2GS —",    # handles light + fan on same relay
        "FP1E",
    ],
    "Bedroom kit — relay": [    # "relay + presence (single switch, no dimming)"
        "ZBMINIR2",
        "FP1E",
    ],
}

# ── Updated Package default_rooms ────────────────────────────────────────────

def _r(room_type, *substrs, custom_name=""):
    return {
        "room_type": room_type,
        "custom_name": custom_name,
        "devices": [{"model_name_contains": s} for s in substrs],
    }

LIVING = ("ZBMINIR2", "MINI-ZB2GS —", "FP1E")
KITCHEN = ("ZBMINIR2", "FP1E", "water / leak", "water / leak", "water / leak")
HALLWAY = ("ZBMINIR2", "FP1E")
BEDROOM_RELAY = ("ZBMINIR2", "FP1E")
BEDROOM_DIMMER_FAN = ("MINI-ZBDIM", "MINI-ZB2GS —", "FP1E")
PRIMARY_BED = ("MINI-ZBDIM", "FP2 60")
BATHROOM = ("ZBMINIR2", "MINI-ZB2GS —", "FP1E", "temperature + humidity", "water / leak")

UPDATED_PACKAGE_ROOMS = {
    "Connected Home — 1 BR / 1 BA": [
        _r("living_room", *LIVING),
        _r("kitchen",     *KITCHEN),
        _r("hallway",     *HALLWAY),
        _r("bedroom",     *BEDROOM_RELAY),
        _r("bathroom",    *BATHROOM),
    ],
    "Connected Home — 2 BR / 2 BA": [
        _r("living_room", *LIVING),
        _r("kitchen",     *KITCHEN),
        _r("hallway",     *HALLWAY),
        _r("bedroom",     *BEDROOM_RELAY),
        _r("bedroom",     *BEDROOM_RELAY),
        _r("bathroom",    *BATHROOM),
        _r("bathroom",    *BATHROOM),
    ],
    "Connected Home — 3 BR / 2 BA": [
        _r("living_room", *LIVING),
        _r("kitchen",     *KITCHEN),
        _r("hallway",     *HALLWAY),
        _r("bedroom",     *PRIMARY_BED,    custom_name="Primary"),
        _r("bedroom",     *BEDROOM_RELAY),
        _r("bedroom",     *BEDROOM_RELAY),
        _r("bathroom",    *BATHROOM),
        _r("bathroom",    *BATHROOM),
    ],
}


def forward(apps, schema_editor):
    CatalogDevice = apps.get_model("jobs", "CatalogDevice")
    Package       = apps.get_model("jobs", "Package")
    RoomDevice    = apps.get_model("jobs", "RoomDevice")

    # 1. Add missing individual-component catalog entries.
    water_sensor, _ = CatalogDevice.objects.get_or_create(
        model_name="Aqara SJCGQ11LM — water / leak sensor",
        defaults={"device_type": "sensor", "active": True},
    )
    humidity_sensor, _ = CatalogDevice.objects.get_or_create(
        model_name="Aqara WSDCGQ11LM — temperature + humidity sensor",
        defaults={"device_type": "sensor", "active": True},
    )

    # 2. Update Package.default_rooms.
    for pkg in Package.objects.filter(active=True):
        if pkg.name in UPDATED_PACKAGE_ROOMS:
            pkg.default_rooms = UPDATED_PACKAGE_ROOMS[pkg.name]
            pkg.save(update_fields=["default_rooms"])

    # 3. Expand existing kit-based RoomDevice rows into individual components.
    #    Sorted longest-key-first so more-specific matches win.
    expansion_keys = sorted(KIT_EXPANSION.keys(), key=len, reverse=True)

    # Build a reusable device lookup (substr → CatalogDevice or None).
    all_substrs = {s for parts in KIT_EXPANSION.values() for s in parts}
    device_lookup = {}
    for substr in all_substrs:
        device_lookup[substr] = (
            CatalogDevice.objects.filter(model_name__icontains=substr, active=True).first()
        )

    kit_rds = list(
        RoomDevice.objects.select_related("device").filter(device__device_type="kit")
    )
    for rd in kit_rds:
        kit_name = rd.device.model_name
        matched_key = next(
            (k for k in expansion_keys if k.lower() in kit_name.lower()),
            None,
        )
        if not matched_key:
            continue  # unknown kit — leave as-is

        components = KIT_EXPANSION[matched_key]
        room = rd.room
        for substr in components:
            dev = device_lookup.get(substr)
            if dev:
                RoomDevice.objects.create(room=room, device=dev, quantity=1)

        rd.delete()


def backward(apps, schema_editor):
    # Revert to kit-based default_rooms (partial — only package data, not room devices).
    CatalogDevice = apps.get_model("jobs", "CatalogDevice")
    Package       = apps.get_model("jobs", "Package")

    ORIGINAL = {
        "Connected Home — 1 BR / 1 BA": [
            {"room_type": "living_room", "devices": [{"model_name_contains": "Living room kit"}]},
            {"room_type": "kitchen",     "devices": [{"model_name_contains": "Kitchen kit"}]},
            {"room_type": "hallway",     "devices": [{"model_name_contains": "Hallway kit"}]},
            {"room_type": "bedroom",     "devices": [{"model_name_contains": "Bedroom kit — relay"}]},
            {"room_type": "bathroom",    "devices": [{"model_name_contains": "Bathroom kit"}]},
        ],
        "Connected Home — 2 BR / 2 BA": [
            {"room_type": "living_room", "devices": [{"model_name_contains": "Living room kit"}]},
            {"room_type": "kitchen",     "devices": [{"model_name_contains": "Kitchen kit"}]},
            {"room_type": "hallway",     "devices": [{"model_name_contains": "Hallway kit"}]},
            {"room_type": "bedroom",     "devices": [{"model_name_contains": "Bedroom kit — relay"}]},
            {"room_type": "bedroom",     "devices": [{"model_name_contains": "Bedroom kit — relay"}]},
            {"room_type": "bathroom",    "devices": [{"model_name_contains": "Bathroom kit"}]},
            {"room_type": "bathroom",    "devices": [{"model_name_contains": "Bathroom kit"}]},
        ],
        "Connected Home — 3 BR / 2 BA": [
            {"room_type": "living_room", "devices": [{"model_name_contains": "Living room kit"}]},
            {"room_type": "kitchen",     "devices": [{"model_name_contains": "Kitchen kit"}]},
            {"room_type": "hallway",     "devices": [{"model_name_contains": "Hallway kit"}]},
            {"room_type": "bedroom",     "custom_name": "Primary", "devices": [{"model_name_contains": "Primary bedroom kit"}]},
            {"room_type": "bedroom",     "devices": [{"model_name_contains": "Bedroom kit — relay"}]},
            {"room_type": "bedroom",     "devices": [{"model_name_contains": "Bedroom kit — relay"}]},
            {"room_type": "bathroom",    "devices": [{"model_name_contains": "Bathroom kit"}]},
            {"room_type": "bathroom",    "devices": [{"model_name_contains": "Bathroom kit"}]},
        ],
    }
    for pkg in Package.objects.filter(active=True):
        if pkg.name in ORIGINAL:
            pkg.default_rooms = ORIGINAL[pkg.name]
            pkg.save(update_fields=["default_rooms"])

    CatalogDevice.objects.filter(
        model_name__in=[
            "Aqara SJCGQ11LM — water / leak sensor",
            "Aqara WSDCGQ11LM — temperature + humidity sensor",
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0015_checklist_and_room_devices"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
