import json
import secrets
import string
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import EmailMessage
from django.db.models import Count, Max
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from .forms import SalesForm
from .models import (
    BackendInstall,
    BackendInstallCapture,
    BackendInstallItemState,
    CatalogDevice,
    ChecklistItem,
    ChecklistTemplate,
    Customer,
    InternalPrep,
    Job,
    Package,
    PairingSheet,
    PairingSheetDevice,
    PreInstallCapture,
    PreInstallChecklist,
    PreInstallItemState,
    Room,
    RoomDevice,
    SaleLine,
)


def _is_staff(user):
    return user.is_authenticated and user.is_staff


staff_required = user_passes_test(_is_staff)


def _alnum(s):
    return "".join(ch for ch in (s or "") if ch.isalnum())


def _purchase_yy(job):
    d = job.sold_on
    if d is None and job.created_at:
        d = job.created_at.date()
    return f"{d.year % 100:02d}" if d else ""


def _hostname_for(customer):
    chunk = _alnum(customer.last_name)[:4].capitalize()
    return f"HA{chunk}" if chunk else ""


def _temp_password_for(customer, job):
    yy = _purchase_yy(job)
    chunk = _alnum(customer.last_name)[:4].capitalize()
    if not (yy and chunk):
        return ""
    return f"HA{yy}!{chunk}"


# Generated once on first page load and saved, so service passwords stay
# stable across reloads. 16 chars of unambiguous alphanumerics — no
# 0/O/1/l/I — is plenty for a LAN-only service the client can rotate.
_UNAMBIGUOUS_ALPHABET = (string.ascii_letters + string.digits).translate(
    str.maketrans("", "", "0Ol1I")
)


def _random_password(length=16):
    return "".join(secrets.choice(_UNAMBIGUOUS_ALPHABET) for _ in range(length))


# Captures that we can derive from the Customer / Job and pre-fill so the
# installer doesn't retype them. Each formula returns a string; falsy
# values are skipped (so a customer with no last name doesn't get a
# malformed hostname). Values are saved to the DB on first page load —
# changing the formula later doesn't retroactively rewrite past values.
PREFILL_FORMULAS = {
    "hostname":         lambda c, j: _hostname_for(c),
    "client_uid":       lambda c, j: (c.first_name or "").lower(),
    "client_display":   lambda c, j: f"{c.first_name} {c.last_name}".strip(),
    "client_temppass":  lambda c, j: _temp_password_for(c, j),
    "home_name":        lambda c, j: f"{c.last_name} Home" if c.last_name else "",
    "mqtt_pass":        lambda c, j: _random_password(),
    "ag_pass":          lambda c, j: _random_password(),
}


def _ensure_prefilled_captures(bi):
    customer = bi.job.customer
    if not customer:
        return set()
    valid_keys = set(ChecklistItem.objects.filter(
        step__template_id=bi.template_id, kind="capture",
    ).values_list("capture_key", flat=True))
    existing = set(bi.captures.values_list("key", flat=True))
    prefilled = set()
    for key, formula in PREFILL_FORMULAS.items():
        if key not in valid_keys or key in existing:
            continue
        value = formula(customer, bi.job)
        if not value:
            continue
        BackendInstallCapture.objects.create(
            backend_install=bi, key=key, value=value,
        )
        prefilled.add(key)
    return prefilled


def _get_or_init_backend_install(job):
    bi, _ = BackendInstall.objects.get_or_create(
        job=job,
        defaults={"template": ChecklistTemplate.current_for("backend-install")},
    )
    if bi.template_id is None:
        bi.template = ChecklistTemplate.current_for("backend-install")
        if bi.template_id is not None:
            bi.save(update_fields=["template"])
    return bi


@login_required
@staff_required
def backend_install_render(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    bi = _get_or_init_backend_install(job)

    if bi.template_id is None:
        # No backend-install template has been ported yet.
        return render(
            request,
            "jobs/backend_install_unavailable.html",
            {"job": job},
            status=503,
        )

    _ensure_prefilled_captures(bi)

    template = bi.template
    steps = list(template.steps.prefetch_related("items").all())
    item_states = {s.item_id: s for s in bi.item_states.all()}
    captures = {c.key: c.value for c in bi.captures.all()}
    prefill_keys = set(PREFILL_FORMULAS)

    rendered_steps = []
    total_checks = total_done = 0
    for step in steps:
        entries = []
        check_total = check_done = 0
        for item in step.items.all():
            entry = {"item": item}
            if item.kind == "check":
                state = item_states.get(item.id)
                entry["checked"] = bool(state and state.checked)
                entry["notes"] = state.notes if state else ""
                check_total += 1
                if entry["checked"]:
                    check_done += 1
            elif item.kind == "capture":
                entry["value"] = captures.get(item.capture_key, "")
                entry["prefilled"] = item.capture_key in prefill_keys
            entries.append(entry)
        rendered_steps.append({
            "step": step,
            "entries": entries,
            "check_done": check_done,
            "check_total": check_total,
        })
        total_checks += check_total
        total_done += check_done

    return render(request, "jobs/backend_install.html", {
        "job": job,
        "backend_install": bi,
        "template": template,
        "steps": rendered_steps,
        "total_checks": total_checks,
        "total_done": total_done,
    })


def _load_json(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return {}


def _checklist_item_for(bi, item_id, kind):
    if bi.template_id is None:
        raise Http404
    return get_object_or_404(
        ChecklistItem,
        pk=item_id,
        step__template_id=bi.template_id,
        kind=kind,
    )


@login_required
@staff_required
@require_POST
def backend_install_toggle_check(request, invoice_number, item_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    bi = _get_or_init_backend_install(job)
    item = _checklist_item_for(bi, item_id, kind="check")

    checked = bool(_load_json(request).get("checked"))
    state, _ = BackendInstallItemState.objects.get_or_create(
        backend_install=bi, item=item,
    )
    state.checked = checked
    state.checked_at = now() if checked else None
    state.checked_by = request.user if checked else None
    state.save(update_fields=["checked", "checked_at", "checked_by"])

    return JsonResponse({"checked": state.checked})


@login_required
@staff_required
@require_POST
def backend_install_save_notes(request, invoice_number, item_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    bi = _get_or_init_backend_install(job)
    item = _checklist_item_for(bi, item_id, kind="check")

    notes = str(_load_json(request).get("notes", ""))
    state, _ = BackendInstallItemState.objects.get_or_create(
        backend_install=bi, item=item,
    )
    state.notes = notes
    state.save(update_fields=["notes"])

    return JsonResponse({"saved": True})


@login_required
@staff_required
@require_POST
def backend_install_save_capture(request, invoice_number, key):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    bi = _get_or_init_backend_install(job)
    if bi.template_id is None or not ChecklistItem.objects.filter(
        step__template_id=bi.template_id, kind="capture", capture_key=key,
    ).exists():
        raise Http404("Unknown capture key for this template")

    value = str(_load_json(request).get("value", ""))
    BackendInstallCapture.objects.update_or_create(
        backend_install=bi, key=key, defaults={"value": value},
    )
    return JsonResponse({"saved": True})


@login_required
@staff_required
@require_POST
def backend_install_reset(request, invoice_number):
    # Clears every check state, every note, and every capture for this
    # job's BackendInstall, then re-snapshots the latest published
    # backend-install template (so a rebuild starts from current content,
    # not an outdated frozen version).
    job = get_object_or_404(Job, invoice_number=invoice_number)
    bi = _get_or_init_backend_install(job)

    bi.item_states.all().delete()
    bi.captures.all().delete()

    latest = ChecklistTemplate.current_for("backend-install")
    if latest is not None and latest.pk != bi.template_id:
        bi.template = latest
        bi.save(update_fields=["template"])

    return JsonResponse({"reset": True})


# ── Pre-install checklist ────────────────────────────────────────────────

def _get_or_init_pre_install(job):
    pi, _ = PreInstallChecklist.objects.get_or_create(
        job=job,
        defaults={"template": ChecklistTemplate.current_for("pre-install")},
    )
    if pi.template_id is None:
        pi.template = ChecklistTemplate.current_for("pre-install")
        if pi.template_id is not None:
            pi.save(update_fields=["template"])
    return pi


def _render_checklist(pi):
    """Return (steps_list, total_checks, total_done) for a PreInstallChecklist."""
    template = pi.template
    steps = list(template.steps.prefetch_related("items").all())
    item_states = {s.item_id: s for s in pi.item_states.all()}
    captures = {c.key: c.value for c in pi.captures.all()}

    rendered_steps = []
    total_checks = total_done = 0
    for step in steps:
        entries = []
        check_total = check_done = 0
        for item in step.items.all():
            entry = {"item": item}
            if item.kind == "check":
                state = item_states.get(item.id)
                entry["checked"] = bool(state and state.checked)
                entry["notes"] = state.notes if state else ""
                check_total += 1
                if entry["checked"]:
                    check_done += 1
            elif item.kind == "capture":
                entry["value"] = captures.get(item.capture_key, "")
                entry["prefilled"] = False
            entries.append(entry)
        rendered_steps.append({
            "step": step,
            "entries": entries,
            "check_done": check_done,
            "check_total": check_total,
        })
        total_checks += check_total
        total_done += check_done
    return rendered_steps, total_checks, total_done


@login_required
@staff_required
def pre_install_checklist_render(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    pi = _get_or_init_pre_install(job)

    if pi.template_id is None:
        return render(
            request,
            "jobs/checklist_unavailable.html",
            {"job": job, "form_name": "Pre-install checklist", "slug": "pre-install"},
            status=503,
        )

    # Advance status from SOLD to PRE_INSTALL when the checklist is first opened.
    if job.status == Job.Status.SOLD:
        job.status = Job.Status.PRE_INSTALL
        job.save(update_fields=["status"])

    # Pre-fill the package_summary capture from the package description if blank.
    if job.package and not pi.captures.filter(key="package_summary").exists():
        desc = job.package.description
        prefill = f"{job.package.name} — {desc}" if desc else job.package.name
        pi.captures.create(key="package_summary", value=prefill)

    rendered_steps, total_checks, total_done = _render_checklist(pi)

    rooms = list(job.rooms.prefetch_related("devices__device").all())
    room_types = [{"value": c[0], "label": c[1]} for c in Room.RoomType.choices]
    catalog_flat = [
        {"device_id": d.id, "label": str(d)}
        for d in CatalogDevice.objects.filter(active=True).exclude(device_type=CatalogDevice.DeviceType.KIT)
    ]

    # Break SaleLines into package vs à-la-carte for correct discount display.
    pkg_list_price = Decimal("0")
    adhoc_price = Decimal("0")
    for sl in job.sale_lines.all():
        val = (sl.unit_cost or Decimal("0")) * sl.quantity
        if sl.from_package:
            pkg_list_price += val
        else:
            adhoc_price += val

    if job.payment_override_amount and not job.payment_override:
        # Auto package-discount: bundle price + adhoc on top.
        package_discount = max(
            Decimal("0"),
            (pkg_list_price - job.payment_override_amount).quantize(Decimal("0.01")),
        )
        total = (job.payment_override_amount + adhoc_price).quantize(Decimal("0.01"))
    else:
        package_discount = Decimal("0")
        total = _sale_total(job).quantize(Decimal("0.01"))

    half = (total / 2).quantize(Decimal("0.01"))

    service_plan_choices = [
        {"value": v, "label": l}
        for v, l in Job.ServicePlan.choices
    ]

    return render(request, "jobs/pre_install_checklist.html", {
        "job": job,
        "pre_install_checklist": pi,
        "template": pi.template,
        "steps": rendered_steps,
        "total_checks": total_checks,
        "total_done": total_done,
        "rooms": rooms,
        "room_types_json": json.dumps(room_types),
        "catalog_json": json.dumps(catalog_flat),
        "sale_total": f"${total}",
        "sale_deposit": f"${half}",
        "package_list_price": f"${pkg_list_price.quantize(Decimal('0.01'))}" if package_discount else None,
        "package_discount": f"${package_discount}" if package_discount else None,
        "adhoc_price": _fmt_adhoc(adhoc_price) if (package_discount and adhoc_price != Decimal("0")) else None,
        "adhoc_label": "Net adjustments" if (package_discount and adhoc_price < Decimal("0")) else "Additional items",
        "service_plan_choices_json": json.dumps(service_plan_choices),
    })


def _pi_checklist_item_for(pi, item_id, kind):
    if pi.template_id is None:
        raise Http404
    return get_object_or_404(
        ChecklistItem,
        pk=item_id,
        step__template_id=pi.template_id,
        kind=kind,
    )


@login_required
@staff_required
@require_POST
def pre_install_toggle_check(request, invoice_number, item_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    pi = _get_or_init_pre_install(job)
    item = _pi_checklist_item_for(pi, item_id, kind="check")

    checked = bool(_load_json(request).get("checked"))
    state, _ = PreInstallItemState.objects.get_or_create(
        pre_install_checklist=pi, item=item,
    )
    state.checked = checked
    state.checked_at = now() if checked else None
    state.checked_by = request.user if checked else None
    state.save(update_fields=["checked", "checked_at", "checked_by"])

    return JsonResponse({"checked": state.checked})


@login_required
@staff_required
@require_POST
def pre_install_save_notes(request, invoice_number, item_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    pi = _get_or_init_pre_install(job)
    item = _pi_checklist_item_for(pi, item_id, kind="check")

    notes = str(_load_json(request).get("notes", ""))
    state, _ = PreInstallItemState.objects.get_or_create(
        pre_install_checklist=pi, item=item,
    )
    state.notes = notes
    state.save(update_fields=["notes"])

    return JsonResponse({"saved": True})


@login_required
@staff_required
@require_POST
def pre_install_save_capture(request, invoice_number, key):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    pi = _get_or_init_pre_install(job)
    if pi.template_id is None or not ChecklistItem.objects.filter(
        step__template_id=pi.template_id, kind="capture", capture_key=key,
    ).exists():
        raise Http404("Unknown capture key for this template")

    value = str(_load_json(request).get("value", ""))
    PreInstallCapture.objects.update_or_create(
        pre_install_checklist=pi, key=key, defaults={"value": value},
    )
    return JsonResponse({"saved": True})


@login_required
@staff_required
@require_POST
def pre_install_reset(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    pi = _get_or_init_pre_install(job)

    pi.item_states.all().delete()
    pi.captures.all().delete()

    latest = ChecklistTemplate.current_for("pre-install")
    if latest is not None and latest.pk != pi.template_id:
        pi.template = latest
        pi.save(update_fields=["template"])

    return JsonResponse({"reset": True})


# ── Sales form ───────────────────────────────────────────────────────────

def _packages_json():
    """Return a JSON-serialisable structure of all active packages + their devices."""
    result = []
    for pkg in Package.objects.filter(active=True).prefetch_related("devices__device"):
        result.append({
            "id": pkg.id,
            "name": pkg.name,
            "description": pkg.description,
            "base_price": str(pkg.base_price) if pkg.base_price is not None else None,
            "devices": [
                {
                    "device_id": pd.device_id,
                    "label": str(pd.device),
                    "quantity": pd.quantity,
                    "unit_cost": str(pd.device.default_cost) if pd.device.default_cost is not None else None,
                }
                for pd in pkg.devices.all()
            ],
        })
    return result


def _catalog_json():
    """Return a JSON-serialisable list of all active catalog devices for à-la-carte selection."""
    result = {}
    for device in CatalogDevice.objects.filter(active=True):
        dtype = device.get_device_type_display()
        result.setdefault(dtype, []).append({
            "device_id": device.id,
            "label": device.model_name,
            "unit_cost": str(device.default_cost) if device.default_cost is not None else None,
        })
    return result


def _create_default_rooms(job, pkg):
    """Auto-create Room rows (with pre-assigned devices) from Package.default_rooms."""
    if not pkg.default_rooms:
        return
    valid_types = {c[0] for c in Room.RoomType.choices}
    device_cache = {}

    for order, entry in enumerate(pkg.default_rooms):
        room_type = entry.get("room_type", "other")
        if room_type not in valid_types:
            room_type = "other"
        room = Room.objects.create(
            job=job,
            room_type=room_type,
            custom_name=entry.get("custom_name", ""),
            order=order,
            from_package=True,
        )
        for dev_spec in entry.get("devices", []):
            substr = dev_spec.get("model_name_contains", "")
            if not substr:
                continue
            if substr not in device_cache:
                device_cache[substr] = CatalogDevice.objects.filter(
                    model_name__icontains=substr, active=True
                ).exclude(device_type=CatalogDevice.DeviceType.KIT).first()
            device = device_cache[substr]
            if device:
                RoomDevice.objects.create(room=room, device=device, quantity=1)


def _backfill_room_devices(job, pkg):
    """Add missing device assignments to package-derived rooms that have none.

    Safe to call on existing jobs: only touches rooms that currently have zero
    devices, so confirmed work already done by the installer is preserved.
    """
    if not pkg.default_rooms:
        return
    device_cache = {}
    # Work against a mutable list so each entry matches at most one room.
    empty_rooms = list(
        job.rooms.filter(from_package=True)
        .annotate(_dc=Count("devices"))
        .filter(_dc=0)
    )
    if not empty_rooms:
        return
    for entry in pkg.default_rooms:
        if not entry.get("devices"):
            continue
        room_type = entry.get("room_type")
        custom_name = entry.get("custom_name", "")
        room = next(
            (r for r in empty_rooms
             if r.room_type == room_type and r.custom_name == custom_name),
            None,
        )
        if not room:
            continue
        empty_rooms.remove(room)
        for dev_spec in entry["devices"]:
            substr = dev_spec.get("model_name_contains", "")
            if not substr:
                continue
            if substr not in device_cache:
                device_cache[substr] = CatalogDevice.objects.filter(
                    model_name__icontains=substr, active=True
                ).exclude(device_type=CatalogDevice.DeviceType.KIT).first()
            device = device_cache[substr]
            if device:
                RoomDevice.objects.create(room=room, device=device, quantity=1)


def _update_sale(job, new_package_id, device_rows):
    """Replace sale lines and package-derived rooms for an existing job.

    Called from the edit-sale form. Keeps manually-added rooms intact and only
    replaces package-sourced sale lines / rooms when the package changes.
    When the package is unchanged, backfills any room device assignments that
    are missing (handles jobs created before the device-mapping migration).
    """
    package_changed = job.package_id != (new_package_id or None)

    if package_changed:
        job.sale_lines.filter(from_package=True).delete()
        job.rooms.filter(from_package=True).delete()
        job.package = None
        job.package_summary = ""
        job.payment_override_amount = None
        job.save(update_fields=["package", "package_summary", "payment_override_amount"])
    elif job.package_id:
        # Package unchanged — backfill devices into any package rooms that lack them.
        try:
            _backfill_room_devices(job, Package.objects.get(pk=job.package_id, active=True))
        except Package.DoesNotExist:
            pass

    # Always refresh à-la-carte lines so the latest quantities/notes are saved.
    job.sale_lines.filter(from_package=False).delete()

    # Re-use the same helper; it handles both package lines and à-la-carte.
    # If the package didn't change, pass None so it skips re-creating package lines.
    _create_sale_lines(job, new_package_id if package_changed else None, device_rows)


def _create_sale_lines(job, package_id, device_rows):
    """Create SaleLine rows from a package expansion + à-la-carte rows."""
    sort = 0

    if package_id:
        try:
            pkg = Package.objects.get(pk=package_id, active=True)
            for pd in pkg.devices.select_related("device"):
                SaleLine.objects.create(
                    job=job,
                    device=pd.device,
                    quantity=pd.quantity,
                    unit_cost=pd.device.default_cost,
                    notes=f"From package: {pkg.name}",
                    from_package=True,
                    sort_order=sort,
                )
                sort += 1
            # Save package FK, summary, and base price on the job.
            update_fields = []
            if not job.package_id:
                job.package = pkg
                update_fields.append("package")
            if not job.package_summary:
                job.package_summary = pkg.name
                update_fields.append("package_summary")
            # Auto-apply the package price as the effective sale total so
            # the bundle discount is reflected without a manual override.
            if pkg.base_price and not job.payment_override_amount:
                job.payment_override_amount = pkg.base_price
                update_fields.append("payment_override_amount")
            if update_fields:
                job.save(update_fields=update_fields)
            _create_default_rooms(job, pkg)
        except Package.DoesNotExist:
            pass

    for row in device_rows:
        try:
            device = CatalogDevice.objects.get(pk=row["device_id"], active=True)
        except CatalogDevice.DoesNotExist:
            continue
        SaleLine.objects.create(
            job=job,
            device=device,
            quantity=row["quantity"],
            unit_cost=device.default_cost,
            notes=row.get("notes", ""),
            from_package=False,
            sort_order=sort,
        )
        sort += 1


def _draft_invoice_number():
    """Unique internal identifier for a new job before the invoice is finalized."""
    return f"DRAFT-{uuid.uuid4().hex[:12].upper()}"


def _generate_display_invoice_number(job):
    """
    Build the formatted customer-facing invoice code:
      YYMMDD + M(1) + RR(2) + AAA(3) + SS(2) = 14 chars

    M   — service plan tier on the job (0=none, 1=Basic, 2=Standard, 3=Premium)
    RR  — room count from the pre-install walkthrough (01–99)
    AAA — number of à-la-carte (non-package) sale lines (001–999)
    SS  — sequence of finalized jobs today (01–99)
    """
    today = date.today()
    date_part = today.strftime("%y%m%d")

    tier = min(9, job.service_plan_tier or 0)

    room_count = min(99, job.rooms.count())
    adhoc_count = min(999, job.sale_lines.filter(from_package=False).count())

    today_seq = Job.objects.filter(
        finalized_at__date=today,
        display_invoice_number__isnull=False,
    ).count()
    sequence = min(99, today_seq + 1)

    return f"{date_part}{tier:01d}{room_count:02d}{adhoc_count:03d}{sequence:02d}"


def _fmt_adhoc(value):
    """Format adhoc Decimal as '$X.XX' or '−$X.XX' for negative values."""
    q = value.quantize(Decimal("0.01"))
    if q < 0:
        return f"−${abs(q)}"
    return f"${q}"


def _sale_total(job, manual_override=None):
    """
    Return the effective sale total as Decimal.

    Priority:
      1. manual_override — a one-time amount entered in the finalize form (true override)
      2. job.payment_override (True) + payment_override_amount — staff-set final price
      3. package auto-discount: payment_override_amount (package bundle price) +
         any à-la-carte lines added on top (from_package=False)
      4. Sum of all SaleLines (no package / fully custom build)
    """
    if manual_override:
        try:
            return Decimal(str(manual_override))
        except InvalidOperation:
            pass
    if job.payment_override_amount:
        if job.payment_override:
            # Staff explicitly set a final price — use as-is.
            return job.payment_override_amount
        # Auto-applied package discount: bundle price + any à-la-carte items on top.
        adhoc = sum(
            ((sl.unit_cost or Decimal("0")) * sl.quantity
             for sl in job.sale_lines.filter(from_package=False)),
            Decimal("0"),
        )
        return job.payment_override_amount + adhoc
    return sum(
        ((sl.unit_cost or Decimal("0")) * sl.quantity
         for sl in job.sale_lines.all()),
        Decimal("0"),
    )


def _sale_line_sum(job):
    """Raw sum of SaleLine costs — used to display the à la carte value."""
    return sum(
        ((sl.unit_cost or Decimal("0")) * sl.quantity
         for sl in job.sale_lines.all()),
        Decimal("0"),
    )


def _send_payment_email(job, invoice_code, override_amount=None):
    """Send the quote / payment options email to the customer."""
    total = _sale_total(job, override_amount)
    half = (total / 2).quantize(Decimal("0.01"))
    total = total.quantize(Decimal("0.01"))

    subject = f"Dark Forest Home Automation — Your quote (Invoice {invoice_code})"
    body = (
        f"Hi {job.customer.first_name},\n\n"
        f"Thank you for choosing Dark Forest Home Automation! "
        f"Here's a summary of your installation quote.\n\n"
        f"Invoice: {invoice_code}\n\n"
        f"Payment options\n"
        f"───────────────────────────────────\n"
        f"  50% deposit:    ${half}\n"
        f"  Full payment:   ${total}\n"
        f"  Other amount:   Reply to discuss — we're happy to work with you.\n"
        f"───────────────────────────────────\n\n"
        f"To confirm your booking, reply to this email with your preferred "
        f"payment amount and we'll send payment instructions.\n\n"
        f"A reminder of our core promise: all devices and accounts are registered "
        f"in your name from day one. You own everything — credentials, hardware, "
        f"and your Home Assistant instance.\n\n"
        f"Questions? Just reply to this email.\n\n"
        f"— Ron\n"
        f"Dark Forest Home Automation\n"
    )

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[job.customer.email],
        reply_to=[settings.DFHA_REPLY_TO_EMAIL],
    )
    email.send(fail_silently=False)


@login_required
@staff_required
def sales_form(request):
    packages = _packages_json()
    catalog = _catalog_json()

    if request.method == "POST":
        form = SalesForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            customer = Customer.objects.create(
                first_name=d["first_name"],
                last_name=d["last_name"],
                email=d["email"],
                phone=d.get("phone", ""),
            )
            invoice_number = _draft_invoice_number()
            job = Job.objects.create(
                invoice_number=invoice_number,
                customer=customer,
                status=Job.Status.SOLD,
                sold_on=d["sold_on"],
                install_date=d.get("install_date"),
                notes=d.get("notes", ""),
                custom_integrations=d.get("custom_integrations", ""),
                custom_automations=d.get("custom_automations", ""),
                service_plan_tier=d.get("service_plan_tier") or 0,
            )
            _create_sale_lines(job, d.get("package_id"), d.get("devices_json") or [])
            return redirect(
                "jobs:pre_install_checklist_render",
                invoice_number=invoice_number,
            )
    else:
        form = SalesForm(initial={"sold_on": now().date()})

    return render(request, "jobs/sales_form.html", {
        "form": form,
        "packages_json": json.dumps(packages),
        "catalog_json": json.dumps(catalog),
    })


@login_required
@staff_required
def sales_form_edit(request, invoice_number):
    """Edit sale details (customer, package, devices) for a non-finalized job.
    When the job is already finalized, renders in read-only view mode."""
    job = get_object_or_404(Job, invoice_number=invoice_number)
    packages = _packages_json()
    catalog = _catalog_json()

    view_only = bool(job.finalized_at)

    if not view_only and request.method == "POST":
        form = SalesForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            # Update customer record in place.
            job.customer.first_name = d["first_name"]
            job.customer.last_name = d["last_name"]
            job.customer.email = d["email"]
            job.customer.phone = d.get("phone", "")
            job.customer.save()
            # Update job fields.
            job.sold_on = d["sold_on"]
            job.install_date = d.get("install_date")
            job.notes = d.get("notes", "")
            job.custom_integrations = d.get("custom_integrations", "")
            job.custom_automations = d.get("custom_automations", "")
            job.service_plan_tier = d.get("service_plan_tier") or 0
            job.save(update_fields=[
                "sold_on", "install_date", "notes",
                "custom_integrations", "custom_automations", "service_plan_tier",
            ])
            old_package_id = job.package_id
            _update_sale(job, d.get("package_id"), d.get("devices_json") or [])
            # If the package changed, refresh the package_summary capture so
            # the pre-install checklist shows the new package description.
            if job.package_id != old_package_id:
                pi = _get_or_init_pre_install(job)
                if job.package_id and job.package:
                    pkg = job.package
                    desc = pkg.description
                    prefill = f"{pkg.name} — {desc}" if desc else pkg.name
                else:
                    prefill = ""
                updated = pi.captures.filter(key="package_summary").update(value=prefill)
                if not updated and prefill:
                    pi.captures.create(key="package_summary", value=prefill)
            return redirect("jobs:pre_install_checklist_render", invoice_number=invoice_number)
    else:
        adhoc_lines = [
            {"device_id": sl.device_id, "quantity": sl.quantity, "notes": sl.notes}
            for sl in job.sale_lines.filter(from_package=False)
        ]
        form = SalesForm(initial={
            "first_name": job.customer.first_name,
            "last_name": job.customer.last_name,
            "email": job.customer.email,
            "phone": job.customer.phone,
            "sold_on": job.sold_on,
            "install_date": job.install_date,
            "notes": job.notes,
            "custom_integrations": job.custom_integrations,
            "custom_automations": job.custom_automations,
            "service_plan_tier": job.service_plan_tier,
            "package_id": job.package_id or "",
        })

    adhoc_lines = [
        {"device_id": sl.device_id, "quantity": sl.quantity, "notes": sl.notes}
        for sl in job.sale_lines.filter(from_package=False)
    ]

    return render(request, "jobs/sales_form.html", {
        "form": form,
        "packages_json": json.dumps(packages),
        "catalog_json": json.dumps(catalog),
        "job": job,
        "edit_mode": True,
        "view_only": view_only,
        "existing_package_id": job.package_id or "",
        "existing_adhoc_json": json.dumps(adhoc_lines),
    })


# ── Internal prep ─────────────────────────────────────────────────────────────

def _get_or_create_internal_prep(job):
    ip, _ = InternalPrep.objects.get_or_create(job=job)
    return ip


@login_required
@staff_required
def internal_prep_render(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    ip = _get_or_create_internal_prep(job)

    rooms = list(job.rooms.prefetch_related("devices__device").order_by("order"))
    for room in rooms:
        devs = list(room.devices.select_related("device").all())
        room.room_devices = devs
        room.cost_subtotal = sum(
            (rd.device.default_cost or Decimal("0")) * rd.quantity for rd in devs
        )
    total_devices = sum(len(r.room_devices) for r in rooms)

    return render(request, "jobs/internal_prep.html", {
        "job": job,
        "internal_prep": ip,
        "rooms": rooms,
        "total_devices": total_devices,
    })


@login_required
@staff_required
@require_POST
def internal_prep_confirm_device(request, invoice_number, sale_line_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    sl = get_object_or_404(SaleLine, pk=sale_line_id, job=job)
    sl.confirmed_in_stock = bool(_load_json(request).get("confirmed"))
    sl.save(update_fields=["confirmed_in_stock"])
    return JsonResponse({"confirmed": sl.confirmed_in_stock})


@login_required
@staff_required
@require_POST
def internal_prep_save_field(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    ip = _get_or_create_internal_prep(job)
    data = _load_json(request)
    field = data.get("field")
    value = data.get("value")

    allowed = {"github_username", "github_created", "picklist_picked", "notes"}
    if field not in allowed:
        raise Http404("Unknown field")

    if field in {"github_created", "picklist_picked"}:
        setattr(ip, field, bool(value))
    else:
        setattr(ip, field, str(value)[:200] if field == "github_username" else str(value))
    ip.save(update_fields=[field])
    return JsonResponse({"saved": True})


# ── Room walkthrough ──────────────────────────────────────────────────────────

@login_required
@staff_required
@require_POST
def room_add(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    data = _load_json(request)
    room_type = data.get("room_type", "")
    if room_type not in {c[0] for c in Room.RoomType.choices}:
        return JsonResponse({"error": "Invalid room type"}, status=400)
    custom_name = str(data.get("custom_name", ""))[:100]
    next_order = (job.rooms.aggregate(m=Max("order"))["m"] or 0) + 1
    room = Room.objects.create(job=job, room_type=room_type, custom_name=custom_name, order=next_order)

    # Pre-populate devices from package when this room type matches a package entry
    devices_added = []
    pkg = job.package if job.package_id else None
    if pkg and pkg.default_rooms:
        matching = [
            e for e in pkg.default_rooms
            if e.get("room_type") == room_type and e.get("custom_name", "") == custom_name
        ]
        if matching:
            existing_count = job.rooms.filter(
                room_type=room_type, custom_name=custom_name
            ).exclude(pk=room.pk).count()
            entry = matching[min(existing_count, len(matching) - 1)]
            device_cache = {}
            for dev_spec in entry.get("devices", []):
                substr = dev_spec.get("model_name_contains", "")
                if not substr:
                    continue
                if substr not in device_cache:
                    device_cache[substr] = CatalogDevice.objects.filter(
                        model_name__icontains=substr, active=True
                    ).exclude(device_type=CatalogDevice.DeviceType.KIT).first()
                device = device_cache[substr]
                if device:
                    rd = RoomDevice.objects.create(room=room, device=device, quantity=1)
                    devices_added.append({
                        "id": rd.id,
                        "device_id": device.id,
                        "device_label": str(device),
                        "quantity": 1,
                        "confirmed": False,
                    })

    return JsonResponse({
        "id": room.id,
        "display_label": room.display_label,
        "room_type": room.room_type,
        "room_type_label": room.get_room_type_display(),
        "custom_name": room.custom_name,
        "devices": devices_added,
    })


@login_required
@staff_required
@require_POST
def room_rename(request, invoice_number, room_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    room = get_object_or_404(Room, pk=room_id, job=job)
    data = _load_json(request)
    room.custom_name = str(data.get("custom_name", ""))[:100].strip()
    room.save(update_fields=["custom_name"])
    return JsonResponse({"custom_name": room.custom_name, "display_label": room.display_label})


@login_required
@staff_required
@require_POST
def room_delete(request, invoice_number, room_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    room = get_object_or_404(Room, pk=room_id, job=job)
    room.delete()
    return JsonResponse({"deleted": True})


@login_required
@staff_required
@require_POST
def room_device_add(request, invoice_number, room_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    room = get_object_or_404(Room, pk=room_id, job=job)
    data = _load_json(request)
    try:
        device = CatalogDevice.objects.get(pk=data.get("device_id"), active=True)
    except CatalogDevice.DoesNotExist:
        return JsonResponse({"error": "Unknown device"}, status=400)
    quantity = max(1, int(data.get("quantity", 1)))
    rd = RoomDevice.objects.create(room=room, device=device, quantity=quantity)
    return JsonResponse({
        "id": rd.id,
        "device_label": str(device),
        "quantity": rd.quantity,
        "confirmed": rd.confirmed,
    })


@login_required
@staff_required
@require_POST
def room_device_delete(request, invoice_number, room_id, rd_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    room = get_object_or_404(Room, pk=room_id, job=job)
    rd = get_object_or_404(RoomDevice, pk=rd_id, room=room)
    rd.delete()
    return JsonResponse({"deleted": True})


@login_required
@staff_required
@require_POST
def room_device_confirm(request, invoice_number, room_id, rd_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    room = get_object_or_404(Room, pk=room_id, job=job)
    rd = get_object_or_404(RoomDevice, pk=rd_id, room=room)
    rd.confirmed = bool(_load_json(request).get("confirmed"))
    rd.save(update_fields=["confirmed"])
    return JsonResponse({"confirmed": rd.confirmed})


@login_required
@staff_required
@require_POST
def room_device_swap(request, invoice_number, room_id, rd_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    room = get_object_or_404(Room, pk=room_id, job=job)
    rd = get_object_or_404(RoomDevice, pk=rd_id, room=room)
    data = _load_json(request)
    try:
        new_device = CatalogDevice.objects.get(pk=int(data.get("device_id", 0)), active=True)
    except (CatalogDevice.DoesNotExist, (ValueError, TypeError)):
        return JsonResponse({"error": "Device not found"}, status=400)

    old_device = rd.device
    if old_device.pk == new_device.pk:
        return JsonResponse({"device_id": new_device.id, "device_label": str(new_device)})

    old_cost = old_device.default_cost or Decimal("0")
    new_cost = new_device.default_cost or Decimal("0")
    delta = new_cost - old_cost

    if delta != Decimal("0"):
        SaleLine.objects.create(
            job=job,
            device=new_device,
            unit_cost=delta,
            quantity=1,
            notes=f"Swap: {old_device.model_name} → {new_device.model_name}"[:200],
            from_package=False,
        )

    rd.device = new_device
    rd.save(update_fields=["device"])
    return JsonResponse({"device_id": new_device.id, "device_label": str(new_device)})


# ── Pick sheet ───────────────────────────────────────────────────────────────

@login_required
@staff_required
def pick_sheet_render(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)

    # Aggregate all room devices by device, regardless of confirmation status.
    quantities: dict[int, dict] = {}
    for room in job.rooms.prefetch_related("devices__device").order_by("order"):
        for rd in room.devices.select_related("device").all():
            did = rd.device_id
            if did not in quantities:
                quantities[did] = {
                    "device": rd.device,
                    "quantity": 0,
                    "source": [],
                }
            quantities[did]["quantity"] += rd.quantity
            label = room.display_label
            if label not in quantities[did]["source"]:
                quantities[did]["source"].append(label)

    # Group by device type.
    by_type: dict[str, list] = defaultdict(list)
    for entry in sorted(quantities.values(), key=lambda e: (e["device"].device_type, -e["quantity"])):
        by_type[entry["device"].get_device_type_display()].append(entry)

    return render(request, "jobs/pick_sheet.html", {
        "job": job,
        "by_type": dict(by_type),
        "total_lines": len(quantities),
    })


# ── Pre-install: custom integrations / automations (AJAX) ────────────────────

@login_required
@staff_required
@require_POST
def pre_install_save_job_text(request, invoice_number):
    """AJAX: save editable job fields from the pre-install checklist."""
    job = get_object_or_404(Job, invoice_number=invoice_number)
    data = _load_json(request)
    field = data.get("field")

    TEXT_FIELDS = {"custom_integrations", "custom_automations"}
    INT_FIELDS = {"service_plan_tier"}

    if field in TEXT_FIELDS:
        value = str(data.get("value", ""))
        setattr(job, field, value)
        job.save(update_fields=[field])
        return JsonResponse({"ok": True})

    if field in INT_FIELDS:
        try:
            value = int(data.get("value", 0))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid value"}, status=400)
        setattr(job, field, value)
        job.save(update_fields=[field])
        return JsonResponse({"ok": True})

    return JsonResponse({"error": "Unknown field"}, status=400)


# ── Pre-install: finalize sale + generate invoice number ──────────────────────

@login_required
@staff_required
@require_POST
def pre_install_finalize(request, invoice_number):
    """
    Finalize the sale: generate display_invoice_number, optionally send the
    payment email, and mark the job as finalized.

    POST body (JSON):
      payment_override  bool   — skip the auto-email
      override_amount   str    — custom total (empty = use SaleLine sum)
    """
    job = get_object_or_404(Job, invoice_number=invoice_number)

    if job.finalized_at:
        return JsonResponse({
            "ok": True,
            "already_finalized": True,
            "invoice_number": job.display_invoice_number,
        })

    data = _load_json(request)
    payment_override = bool(data.get("payment_override", False))
    override_amount_raw = str(data.get("override_amount", "")).strip()
    override_amount = None
    if override_amount_raw:
        try:
            override_amount = Decimal(override_amount_raw)
            if override_amount <= 0:
                override_amount = None
        except InvalidOperation:
            override_amount = None

    display_inv = _generate_display_invoice_number(job)

    email_sent = False
    email_error = None
    if not payment_override:
        try:
            _send_payment_email(job, display_inv, override_amount)
            email_sent = True
        except Exception as exc:
            email_error = str(exc)

    job.display_invoice_number = display_inv
    job.finalized_at = now()
    job.payment_override = payment_override
    if override_amount is not None:
        job.payment_override_amount = override_amount
    job.save(update_fields=[
        "display_invoice_number", "finalized_at",
        "payment_override", "payment_override_amount",
    ])

    total = _sale_total(job, override_amount)
    half = (total / 2).quantize(Decimal("0.01"))

    return JsonResponse({
        "ok": True,
        "invoice_number": display_inv,
        "email_sent": email_sent,
        "email_error": email_error,
        "total": str(total.quantize(Decimal("0.01"))),
        "deposit": str(half),
    })


@login_required
@staff_required
@require_POST
def pre_install_payment_received(request, invoice_number):
    """AJAX: toggle payment_received on the Job."""
    job = get_object_or_404(Job, invoice_number=invoice_number)
    data = _load_json(request)
    received = bool(data.get("received", False))
    job.payment_received = received
    job.payment_received_at = now() if received else None
    job.save(update_fields=["payment_received", "payment_received_at"])
    return JsonResponse({"ok": True, "received": received})


@login_required
@staff_required
@require_POST
def pre_install_toggle_invoice_sent(request, invoice_number):
    """AJAX: toggle invoice_sent on the PreInstallChecklist."""
    job = get_object_or_404(Job, invoice_number=invoice_number)
    pi = _get_or_init_pre_install(job)
    data = _load_json(request)
    sent = bool(data.get("sent", False))
    pi.invoice_sent = sent
    pi.invoice_sent_at = now() if sent else None
    pi.save(update_fields=["invoice_sent", "invoice_sent_at"])
    return JsonResponse({"ok": True, "sent": sent})


# ── Installer home / pipeline view ──────────────────────────────────────

# Stages shown as expanded sections, in the order a job progresses.
ACTIVE_STAGES = [
    Job.Status.SOLD,
    Job.Status.PRE_INSTALL,
    Job.Status.BACKEND,
    Job.Status.PAIRING,
    Job.Status.AUTOMATION,
    Job.Status.ONSITE,
    Job.Status.WALKTHROUGH,
]
ARCHIVE_STAGES = [Job.Status.COMPLETE, Job.Status.CANCELLED]


def _next_action(job):
    if job.status in {Job.Status.SOLD, Job.Status.PRE_INSTALL}:
        return (
            reverse("jobs:pre_install_checklist_render", args=[job.invoice_number]),
            "Open pre-install checklist",
        )
    if job.status == Job.Status.BACKEND:
        return (
            reverse("jobs:backend_install_render", args=[job.invoice_number]),
            "Open backend install",
        )
    if job.status == Job.Status.PAIRING:
        return (
            reverse("jobs:pairing_sheet_render", args=[job.invoice_number]),
            "Open pairing sheet",
        )
    return (
        reverse("admin:jobs_job_change", args=[job.invoice_number]),
        "Open in admin",
    )


def _progress_summary(job, backend_check_totals):
    # Quick progress text shown on each card based on the stage's active
    # record. Only backend install reports a check count today.
    if job.status != Job.Status.BACKEND:
        return None
    try:
        bi = job.backend_install
    except BackendInstall.DoesNotExist:
        return None
    if not bi.template_id:
        return None
    total = backend_check_totals.get(bi.template_id, 0)
    if not total:
        return None
    done = bi.item_states.filter(checked=True).count()
    return {"label": "Backend", "done": done, "total": total}


def _card(job, backend_check_totals):
    url, label = _next_action(job)
    return {
        "job": job,
        "next_url": url,
        "next_label": label,
        "progress": _progress_summary(job, backend_check_totals),
    }


@login_required
@staff_required
def home_dashboard(request):
    jobs = (
        Job.objects
        .select_related("customer")
        .prefetch_related("backend_install")
        .order_by("install_date", "-created_at")
    )

    # Pre-compute total check count per ChecklistTemplate so each card's
    # progress doesn't fire its own COUNT query.
    backend_check_totals = dict(
        ChecklistItem.objects
        .filter(kind="check")
        .values_list("step__template_id")
        .annotate(n=Count("id"))
        .values_list("step__template_id", "n")
    )

    archived_statuses = {s.value for s in ARCHIVE_STAGES}
    grouped = {s.value: [] for s in ACTIVE_STAGES}
    archive = []
    internal_prep_cards = []

    for job in jobs:
        card = _card(job, backend_check_totals)
        if job.status in archived_statuses:
            archive.append(card)
        elif job.status in grouped:
            grouped[job.status].append(card)
        # Collect finalized (invoiced) active jobs for the prep section.
        # Once pre-install is finalized, internal prep and backend install
        # can run in parallel — surface both buttons on the same card.
        if job.finalized_at and job.status not in archived_statuses:
            internal_prep_cards.append({
                "job": job,
                "actions": [
                    {
                        "url": reverse("jobs:internal_prep_render", args=[job.invoice_number]),
                        "label": "Internal prep",
                    },
                    {
                        "url": reverse("jobs:backend_install_render", args=[job.invoice_number]),
                        "label": "Backend install",
                    },
                ],
            })

    stages = [
        {
            "key": s.value,
            "label": s.label,
            "cards": grouped[s.value],
        }
        for s in ACTIVE_STAGES
    ]

    return render(request, "jobs/home.html", {
        "stages": stages,
        "archive": archive,
        "total_active": sum(len(s["cards"]) for s in stages),
        "total_archive": len(archive),
        "internal_prep_cards": internal_prep_cards,
    })


# ── Pairing sheet ────────────────────────────────────────────────────────────
#
# The pairing sheet is the installer's worksheet during the "Pairing" stage:
# every paired device gets a stable HA / Z2M friendly name derived from
# {room_slug}_{device_kind}_{function_slug}. Names are pre-filled by formula
# and remain editable until the sheet is locked.


# Room-slug map ported from internal/planner.html toSlug(). Keyed by (room_type,
# lowercased custom_name); custom_name "" is the fallback for that room_type.
# Multiple matches resolve to the first hit; specific names like "Primary"
# inside a Bedroom collapse to a "_primary" suffix.
_ROOM_NAME_HINTS = [
    ("primary", "primary"),
    ("master",  "primary"),
    ("main",    "main"),
    ("guest",   "guest"),
    ("secondary", "secondary"),
    ("kids",    "kids"),
]


def _room_slug(room):
    """Slug-safe, formula-friendly token for a room. Mirrors planner.html toSlug()."""
    rt = room.room_type
    custom = (room.custom_name or "").strip().lower()
    suffix = ""
    if custom:
        for needle, token in _ROOM_NAME_HINTS:
            if needle in custom:
                suffix = token
                break
        if not suffix:
            # Fallback: free-form custom name → sanitized token.
            suffix = "".join(ch if ch.isalnum() else "_" for ch in custom)
            suffix = "_".join(p for p in suffix.split("_") if p)

    # Canonical room-type base.
    base_map = {
        Room.RoomType.LIVING_ROOM: "living",
        Room.RoomType.KITCHEN:     "kitchen",
        Room.RoomType.DINING_ROOM: "dining",
        Room.RoomType.BEDROOM:     "bedroom",
        Room.RoomType.BATHROOM:    "bathroom",
        Room.RoomType.OFFICE:      "office",
        Room.RoomType.GARAGE:      "garage",
        Room.RoomType.BASEMENT:    "basement",
        Room.RoomType.LAUNDRY:     "laundry",
        Room.RoomType.HALLWAY:     "hallway",
        Room.RoomType.ENTRYWAY:    "entry",
        Room.RoomType.OUTDOOR:     "outdoor",
        Room.RoomType.OTHER:       "room",
    }
    base = base_map.get(rt, rt)
    return f"{base}_{suffix}" if suffix else base


# Maps CatalogDevice.device_type → the {kind} token used in the formula.
_DEVICE_KIND_TOKEN = {
    CatalogDevice.DeviceType.RELAY:  "relay",
    CatalogDevice.DeviceType.SENSOR: "sensor",
    CatalogDevice.DeviceType.PLUG:   "plug",
    CatalogDevice.DeviceType.CAMERA: "camera",
    CatalogDevice.DeviceType.LOCK:   "lock",
    CatalogDevice.DeviceType.SWITCH: "switch",
    CatalogDevice.DeviceType.THERMOSTAT: "thermostat",
    CatalogDevice.DeviceType.HUB:    "hub",
    CatalogDevice.DeviceType.ACCESS_POINT: "ap",
    CatalogDevice.DeviceType.NUC:    "nuc",
    # KIT / OTHER intentionally absent — no canonical name.
}


def _device_kind_token(device):
    return _DEVICE_KIND_TOKEN.get(device.device_type, "")


def _ha_name_for(room, device, instance_index, instance_count):
    """Return the formula-generated HA friendly name, or '' if any token is missing."""
    room_part = _room_slug(room)
    kind = _device_kind_token(device)
    fn = (device.function_slug or "").strip()
    if not (room_part and kind):
        return ""
    parts = [room_part, kind]
    if fn:
        parts.append(fn)
    name = "_".join(parts)
    if instance_count > 1:
        name = f"{name}_{instance_index}"
    return name


def _get_or_init_pairing_sheet(job):
    """Return the PairingSheet for this job, creating it if needed."""
    ps, _ = PairingSheet.objects.get_or_create(job=job)
    return ps


def _sync_pairing_rows(ps):
    """Ensure PairingSheetDevice rows mirror current RoomDevice quantities.

    Adds missing rows (with formula-generated ha_name) and deletes orphans for
    RoomDevices that were removed or had their quantity reduced. Never overrides
    a row's ha_name once it's been edited; only the auto-filled empty rows pick
    up a freshly-computed name. Skipped entirely when the sheet is locked.
    """
    if ps.locked:
        return

    job = ps.job
    rooms = (
        job.rooms
        .prefetch_related("devices__device")
        .order_by("order", "id")
    )

    existing = {
        (psd.room_device_id, psd.instance_index): psd
        for psd in ps.device_rows.all()
    }
    wanted_keys = set()

    for room in rooms:
        for rd in room.devices.select_related("device").all():
            qty = max(rd.quantity, 1)
            for idx in range(1, qty + 1):
                wanted_keys.add((rd.id, idx))
                if (rd.id, idx) in existing:
                    continue
                ha = _ha_name_for(room, rd.device, idx, qty)
                PairingSheetDevice.objects.create(
                    pairing_sheet=ps,
                    room_device=rd,
                    instance_index=idx,
                    ha_name=ha,
                )

    # Remove rows that no longer correspond to a RoomDevice instance.
    orphan_ids = [
        psd.id for key, psd in existing.items()
        if key not in wanted_keys
    ]
    if orphan_ids:
        PairingSheetDevice.objects.filter(id__in=orphan_ids).delete()


def _get_pairing_row(job, psd_id):
    return get_object_or_404(
        PairingSheetDevice.objects.select_related(
            "pairing_sheet", "room_device__room", "room_device__device",
        ),
        pk=psd_id,
        pairing_sheet__job=job,
    )


@login_required
@staff_required
def pairing_sheet_render(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    ps = _get_or_init_pairing_sheet(job)
    _sync_pairing_rows(ps)

    rows_by_room: dict[int, dict] = {}
    for psd in (
        ps.device_rows
        .select_related("room_device__room", "room_device__device")
        .order_by("room_device__room__order", "room_device__room_id", "room_device_id", "instance_index")
    ):
        room = psd.room_device.room
        bucket = rows_by_room.setdefault(
            room.id,
            {"room": room, "room_slug": _room_slug(room), "rows": []},
        )
        bucket["rows"].append(psd)

    rooms = list(rows_by_room.values())
    total_devices = sum(len(b["rows"]) for b in rooms)
    paired_count = sum(1 for b in rooms for r in b["rows"] if r.paired)
    remaining = total_devices - paired_count

    return render(request, "jobs/pairing_sheet.html", {
        "job": job,
        "pairing_sheet": ps,
        "rooms": rooms,
        "total_devices": total_devices,
        "paired_count": paired_count,
        "remaining": remaining,
    })


@login_required
@staff_required
@require_POST
def pairing_sheet_toggle_paired(request, invoice_number, psd_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    psd = _get_pairing_row(job, psd_id)
    if psd.pairing_sheet.locked:
        return JsonResponse({"error": "Pairing sheet is locked."}, status=409)
    paired = bool(_load_json(request).get("paired", False))
    psd.paired = paired
    psd.paired_at = now() if paired else None
    psd.paired_by = request.user if paired else None
    psd.save(update_fields=["paired", "paired_at", "paired_by"])
    return JsonResponse({
        "ok": True,
        "paired": psd.paired,
        "paired_at": psd.paired_at.isoformat() if psd.paired_at else None,
    })


@login_required
@staff_required
@require_POST
def pairing_sheet_save_name(request, invoice_number, psd_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    psd = _get_pairing_row(job, psd_id)
    if psd.pairing_sheet.locked:
        return JsonResponse({"error": "Pairing sheet is locked."}, status=409)
    name = str(_load_json(request).get("ha_name", "")).strip()
    psd.ha_name = name[:120]
    psd.save(update_fields=["ha_name"])
    return JsonResponse({"ok": True, "ha_name": psd.ha_name})


@login_required
@staff_required
@require_POST
def pairing_sheet_save_notes(request, invoice_number, psd_id):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    psd = _get_pairing_row(job, psd_id)
    if psd.pairing_sheet.locked:
        return JsonResponse({"error": "Pairing sheet is locked."}, status=409)
    notes = str(_load_json(request).get("notes", ""))[:200]
    psd.notes = notes
    psd.save(update_fields=["notes"])
    return JsonResponse({"ok": True, "notes": psd.notes})


@login_required
@staff_required
@require_POST
def pairing_sheet_regenerate_name(request, invoice_number, psd_id):
    """Reset a single row's ha_name to the formula-generated value."""
    job = get_object_or_404(Job, invoice_number=invoice_number)
    psd = _get_pairing_row(job, psd_id)
    if psd.pairing_sheet.locked:
        return JsonResponse({"error": "Pairing sheet is locked."}, status=409)
    rd = psd.room_device
    qty = max(rd.quantity, 1)
    psd.ha_name = _ha_name_for(rd.room, rd.device, psd.instance_index, qty)
    psd.save(update_fields=["ha_name"])
    return JsonResponse({"ok": True, "ha_name": psd.ha_name})


@login_required
@staff_required
@require_POST
def pairing_sheet_lock(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    ps = _get_or_init_pairing_sheet(job)
    if not ps.locked:
        ps.locked = True
        ps.locked_at = now()
        ps.locked_by = request.user
        if ps.completed_at is None:
            ps.completed_at = ps.locked_at
        ps.save(update_fields=["locked", "locked_at", "locked_by", "completed_at"])
    return JsonResponse({
        "ok": True,
        "locked": True,
        "locked_at": ps.locked_at.isoformat() if ps.locked_at else None,
    })


@login_required
@staff_required
@require_POST
def pairing_sheet_unlock(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)
    ps = _get_or_init_pairing_sheet(job)
    if ps.locked:
        ps.locked = False
        ps.locked_at = None
        ps.locked_by = None
        ps.save(update_fields=["locked", "locked_at", "locked_by"])
    return JsonResponse({"ok": True, "locked": False})
