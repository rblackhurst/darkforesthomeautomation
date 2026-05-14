# INTERNAL — DFHA EYES ONLY

**Dark Forest Home Automation, LLC · Internal pricing & margin reference**
Session 6 canonical source · April 2026 · **Not for client distribution**

> **Reading this document.** Client price is what we charge. Our cost is BOM hardware only —
> labor, shop time, on-site time, vehicle, and overhead are not subtracted. Treat the gap between
> client price and our cost as gross before labor. Kit margin numbers below are indicative; actual
> labor varies by site condition.

---

## Backend Setup

| Item | Client | Our cost | Notes |
|------|-------:|----------:|-------|
| Backend setup (every install) | $499 | $220–$240 | Intel N100 NUC. Includes Sonoff Zigbee Dongle Plus, HAOS, Z2M, AdGuard, Tailscale, VLAN, backups, app, ownership doc, walkthrough, 2–3 hrs labor. |

---

## UPS — Uninterruptible Power Supply

| Item | À la carte | Bundled | Our cost | Notes |
|------|----------:|---------:|---------:|-------|
| APC Back-UPS 600VA | $149 | +$100 | $83.99 | USB to NUC. Covers NUC + NAS + router + switch. À la carte margin ≈ $65; bundled margin ≈ $16. The $49 bundle delta drives package take-rate. |

---

## Room Kits — Indoor Comfort

| Kit | Client | BOM notes |
|-----|-------:|-----------|
| Basic room (light + presence) | $299 | ZBMINIR2 or ZBMINIL2 + Tuya mmWave |
| Living room (light + fan + presence) | $349 | ZBMINIR2 light + MINI-ZB2GS fan + Tuya mmWave |
| Bedroom — relay + presence (no dimming, single switch) | $299 | ZBMINIR2 or ZBMINIL2 + Tuya mmWave |
| Bedroom — dual relay + fan + presence (no dimming) | $349 | MINI-ZB2GS + Tuya mmWave |
| Bedroom — dimmer + presence (single switch) | $349 | MINI-ZBDIM + Tuya mmWave |
| Bedroom — dimmer + fan relay + presence | $399 | MINI-ZBDIM + MINI-ZB2GS-L + Tuya mmWave |
| Primary bedroom (dimming + Aqara FP2) | $499 | MINI-ZBDIM + Aqara FP2 60GHz |
| Hallway (presence-based lighting) | $299 | ZBMINIR2 or ZBMINIL2 + Tuya mmWave |

---

## Room Kits — Indoor Safety

| Kit | Client | BOM notes |
|-----|-------:|-----------|
| Kitchen (light + presence + 3× water) | $399 | ZBMINIR2 + Tuya mmWave + 3× water |
| Bathroom (light + fan + presence + humidity + water) | $369 | 2× ZBMINIR2 + Tuya mmWave + humidity + 2× water |
| Bathroom double vanity add-on | +$15 | Additional water sensor at second sink |
| Garage Standard (light + tilt + presence) | $379 | ZBMINIR2 + tilt + Tuya mmWave |
| Garage Premium (Standard + camera + opener + contact + vibration) | $599 | Adds Reolink E1 + dry contact opener + man door contact + 2× vibration |
| Second garage door add-on | $149 | Tilt + opener relay + automation |
| Laundry room (light + presence + power + vibration + water) | $299 | ZBMINIR2 + Tuya mmWave + power plug + vibration + water |

---

## Entry Kits

| Kit | Client | BOM notes |
|-----|-------:|-----------|
| Front porch — welcome home + Reolink WiFi doorbell | $449 | ZBMINIR2 porch light + Reolink Video Doorbell WiFi + Chime V2 |
| Front door security (smart lock + approach + entry) | $349 + lock | Presence at entry + contact sensor + lock integration |

---

## Smart Lock Options

| Lock | Client | Hardware (our cost) | Notes |
|------|-------:|--------------------:|-------|
| Level Bolt (Bluetooth, invisible) | $299 | ~$180 | Interior only. ESP32 proxy if needed. |
| Aqara U100 / U200 (Zigbee, keypad + NFC) | $349 | ~$160 | Replaces deadbolt. |
| Aqara U400 (Zigbee, fingerprint + NFC + keypad) | $399 | ~$230 | Premium. Replaces deadbolt. |

---

## Hallway and Stairwell Kits

| Kit | Client | BOM notes |
|-----|-------:|-----------|
| Two-switch stairwell (3-way, presence approach) | $349 | Presence replaces 3-way complexity |
| Three-switch hallway (4-way) | $399 | Presence-based, SNZB-01P at secondary locations |

---

## Outdoor and Perimeter Kits

| Kit | Client | BOM notes |
|-----|-------:|-----------|
| Perimeter lighting (up to 3 exterior lights + dusk/dawn + scene) | $499 | Up to 3 ZBMINIR2 + automations |
| Additional exterior light (beyond 3) | +$79 | Per light |
| Perimeter sensors (up to 3 gate/door) | $299 | Up to 3 contact sensors flush-drilled |
| Additional perimeter sensor (beyond 3) | +$29 | Per sensor |
| Backyard bundle (lighting + sensors + back door) | $649 | Combines lighting and sensor kits |
| Full perimeter (backyard + Reolink NVR + 2 cameras) | from $1,349 | Reolink RLN8-410 + 2× PoE cameras |

---

## Contact Sensors — Invisible Flush-Drill Install

| Item | Client | Our cost | Notes |
|------|-------:|---------:|-------|
| Contact sensor (per sensor) | $5.00 | $2.25 | DP-ZD001 or DP-ZD003 ($2.00) + 3D-printed container ($0.25). Working price — update when wholesale vendor confirmed. |

---

## Connected Home Packages — Bundle Discount ≈ 10%

| Package | À la carte | Package price | Savings |
|---------|----------:|--------------:|--------:|
| Connected Home — 1 BR / 1 BA | $2,563 | $2,249 | $314 |
| Connected Home — 2 BR / 2 BA | $3,281 | $2,899 | $382 |
| Connected Home — 3 BR / 2 BA | $3,630 | $3,199 | $431 |

All Connected Home packages include the UPS at the bundled $100 rate. À la carte column reflects
the same kits + UPS at the $149 stand-alone price. **Standing on-site offer:** any room added at
the time of original install — 10% off kit price.

---

## Per-Room Add-Ons

| Add-on | Client | BOM |
|--------|-------:|-----|
| 3-way scene switch at second location | +$49 | SNZB-01P wireless scene button |
| Dimmer module upgrade | +$39 | MINI-ZBDIM in-wall dimmer |
| Inovelli Blue Series wallplate dimmer (paddle) | +$60 | VZM31-SN. Aeotec bypass (~$10) required for no-neutral installs |
| Fan on/off dual relay | +$39 | MINI-ZB2GS or MINI-ZB2GS-L |
| Aqara FP1E presence sensor upgrade | +$49 | Over standard Tuya mmWave |
| Aqara FP2 60GHz presence sensor upgrade | +$129 | Over standard Tuya mmWave |
| Second presence sensor (large room) | +$79 | Additional Tuya mmWave |
| Fan speed control | TBD on site | Hardware varies by fan model |
| Grocy household inventory setup | +$50 | Software config only |
| Zigbee smart plug — lamp or appliance control | +$49 | ThirdReality smart plug |

---

## Kiosk Tablet — Wall-Mounted Control Panel

| Item | Client | Notes |
|------|-------:|-------|
| Small kiosk — Lenovo Tab M9 9" (full install) | TBD | Pending tablet testing |
| Full kiosk — Samsung Galaxy Tab A9+ 11" (full install) | TBD | Pending tablet testing |
| Config only — client supplies tablet and mount | TBD | Pending tablet testing |
| Additional kiosk same visit | TBD | Discounted, pending testing |

Three tablets ordered for testing (Lenovo Tab M9 2nd gen TB310FU 4GB/64GB plus two others).
Validate full Android (not Go), Fully Kiosk Browser, and time both shop prep and on-site install
before setting prices.

---

## Monitoring Plans

| Plan | Monthly | Annual | Includes |
|------|--------:|-------:|---------|
| Basic | $29/mo | — | Uptime checks + low-battery alerts |
| Standard | $49/mo | $539/yr | Basic + updates + automation tweaks + battery kit at 6 months. Annual saves 1 month. |
| Premium | $79/mo | $790/yr | Standard + priority same-day response + annual on-site visit + annual battery replacement. Annual saves 2 months. |

**Monitoring tier mapping for invoice number digit (M):**
- 0 = no monitoring / monitoring not yet selected
- 1 = Basic ($29/mo)
- 2 = Standard ($49/mo)
- 3 = Premium ($79/mo)

---

## Internal Hardware Costs — Relay Lineup

| Device | Model | Our cost | Notes |
|--------|-------|----------:|-------|
| Single relay, neutral required | ZBMINIR2 | $13–$16 | Standard light on/off. Mesh router. 10A. |
| Single relay, no neutral | ZBMINIL2 | $11–$16 | Older homes. End device only. 6A. |
| Dual relay, neutral required | MINI-ZB2GS | $17.90 | Light + fan same box. Mesh router. 16A. |
| Dual relay, no neutral | MINI-ZB2GS-L | ~$18 | Light + fan, no neutral. End device. 12A. |
| In-wall dimmer, neutral required | MINI-ZBDIM | $26.90 | Dimmable LED. 200VA max. Mesh router. |
| Wallplate dimmer, paddle only | Inovelli VZM31-SN | $60 | Neutral or no-neutral with Aeotec bypass (~$10) |
| Wireless scene switch | SNZB-01P | $12 | 3-way / 4-way second location. CR2477 5yr battery. |

**Two dimming paths:** MINI-ZBDIM behind existing switch (cheaper, neutral required) or Inovelli
VZM31-SN wallplate replacement (premium upsell, paddle only). Aeotec bypass adds ~$10 to
no-neutral Inovelli installs.

---

## Internal Hardware Costs — Sensors and Devices

| Device | Our cost | Notes |
|--------|----------:|-------|
| Tuya Zigbee mmWave presence sensor | $25 | Budget standard |
| Aqara FP1E presence sensor | $49.99 | Upgrade tier 1 |
| Aqara FP2 60GHz presence sensor | $63–$85 | Upgrade tier 2. WiFi. |
| Contact sensor (DP-ZD001 / DP-ZD003) | $2.00 | Plus $0.25 3D-printed container |
| Water / leak sensor | $10 | Tuya Zigbee |
| Vibration sensor | $13 | Tuya Zigbee |
| Tilt sensor (garage door) | $10 | Tuya Zigbee |
| Humidity sensor | — | Included in bathroom kit BOM |
| ThirdReality smart plug (standard) | $12 | On/off lamp or appliance control |
| ThirdReality smart plug (power monitoring) | $12 | Washing machine cycle detection |
| Dry contact relay (garage opener) | $20 | Low-voltage opener terminals |
| Reolink E1 indoor pan/tilt camera | $40 | WiFi, local only |
| Reolink Video Doorbell WiFi + Chime V2 | $100–$115 | Wired, uses existing doorbell wiring |
| Reolink RLN8-410 NVR 8-port PoE 2TB | $285 | 2–4 camera installs |
| APC Back-UPS 600VA | $83.99 | USB to NUC. Covers NUC + NAS + router + switch. |
| 32GB mini USB drive (backup) | ~$8–$10 | Rear port, permanent install |
| Aeotec bypass (Inovelli no-neutral) | ~$10 | Required for VZM31-SN no-neutral install |

---

## Operating Notes

- **Contact sensor working price.** $5.00/unit is a working price — revisit when wholesale vendor
  is confirmed.
- **Garage Premium and second garage door prices** confirmed Session 6.
- **Laundry room kit price** confirmed Session 6.
- **Stair footlight kits removed** pending business establishment — add back later.
- **Backend cost.** N100 NUC at $220–$240 is the dominant variable in backend BOM. Other backend
  items (Sonoff Dongle Plus, USB drive, miscellaneous) total roughly $50–$70.
- **Hardware corrections in force:** ZBMINI-D2 does not exist — use ZBMINIR2.
  SNZB-01 is superseded — use SNZB-01P.
- **Always confirm part numbers** against current Sonoff / Aqara / Reolink product lines before
  quoting.
