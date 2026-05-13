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
        for d in CatalogDevice.objects.filter(active=True)
    ]

    total = _sale_total(job)
    line_sum = _sale_line_sum(job)
    half = (total / 2).quantize(Decimal("0.01"))
    package_discount = (line_sum - total).quantize(Decimal("0.01")) if line_sum > total else Decimal("0")

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
        "sale_total": f"${total.quantize(Decimal('0.01'))}",
        "sale_deposit": f"${half}",
        "sale_line_sum": f"${line_sum.quantize(Decimal('0.01'))}",
        "package_discount": f"${package_discount}" if package_discount else None,
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
    """Auto-create Room rows from Package.default_rooms when a package is sold."""
    if not pkg.default_rooms:
        return
    valid_types = {c[0] for c in Room.RoomType.choices}
    for order, entry in enumerate(pkg.default_rooms):
        room_type = entry.get("room_type", "other")
        if room_type not in valid_types:
            room_type = "other"
        Room.objects.create(
            job=job,
            room_type=room_type,
            custom_name=entry.get("custom_name", ""),
            order=order,
            from_package=True,
        )


def _update_sale(job, new_package_id, device_rows):
    """Replace sale lines and package-derived rooms for an existing job.

    Called from the edit-sale form. Keeps manually-added rooms intact and only
    replaces package-sourced sale lines / rooms when the package changes.
    """
    package_changed = job.package_id != (new_package_id or None)

    if package_changed:
        job.sale_lines.filter(from_package=True).delete()
        job.rooms.filter(from_package=True).delete()
        job.package = None
        job.package_summary = ""
        job.payment_override_amount = None
        job.save(update_fields=["package", "package_summary", "payment_override_amount"])

    # Always refresh à-la-carte lines so the latest quantities/notes are saved.
    job.sale_lines.filter(from_package=False).delete()

    # Re-use the same helper; it handles both package lines and à-la-carte.
    # If the package didn't change, pass None so it skips re-creating package lines.
    _create_sale_lines(job, new_package_id if package_changed else None, device_rows)

    # If package unchanged but à-la-carte changed, payment_override_amount is already
    # set from the original package application — no adjustment needed.


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


def _sale_total(job, manual_override=None):
    """
    Return the effective sale total as Decimal.

    Priority:
      1. manual_override — a one-time amount entered in the finalize form
      2. job.payment_override_amount — persisted override (auto-set to
         package.base_price when a package is applied; can be adjusted)
      3. Sum of SaleLines (à la carte fallback)
    """
    if manual_override:
        try:
            return Decimal(str(manual_override))
        except InvalidOperation:
            pass
    if job.payment_override_amount:
        return job.payment_override_amount
    return sum(
        (sl.unit_cost or Decimal("0")) * sl.quantity
        for sl in job.sale_lines.all()
    )


def _sale_line_sum(job):
    """Raw sum of SaleLine costs — used to display the à la carte value."""
    return sum(
        (sl.unit_cost or Decimal("0")) * sl.quantity
        for sl in job.sale_lines.all()
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
    """Edit sale details (customer, package, devices) for a non-finalized job."""
    job = get_object_or_404(Job, invoice_number=invoice_number)

    if job.finalized_at:
        return redirect("jobs:pre_install_checklist_render", invoice_number=invoice_number)

    packages = _packages_json()
    catalog = _catalog_json()

    if request.method == "POST":
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
            _update_sale(job, d.get("package_id"), d.get("devices_json") or [])
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
    sale_lines = list(job.sale_lines.select_related("device").all())
    total_confirmed = sum(1 for sl in sale_lines if sl.confirmed_in_stock)
    return render(request, "jobs/internal_prep.html", {
        "job": job,
        "internal_prep": ip,
        "sale_lines": sale_lines,
        "total_confirmed": total_confirmed,
        "all_confirmed": len(sale_lines) > 0 and total_confirmed == len(sale_lines),
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
    return JsonResponse({
        "id": room.id,
        "display_label": room.display_label,
        "room_type": room.room_type,
        "custom_name": room.custom_name,
    })


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


# ── Pick sheet ───────────────────────────────────────────────────────────────

@login_required
@staff_required
def pick_sheet_render(request, invoice_number):
    job = get_object_or_404(Job, invoice_number=invoice_number)

    # Combine sale lines + confirmed room devices, deduplicating by device.
    quantities: dict[int, dict] = {}

    for sl in job.sale_lines.select_related("device").all():
        did = sl.device_id
        if did not in quantities:
            quantities[did] = {
                "device": sl.device,
                "quantity": 0,
                "source": [],
            }
        quantities[did]["quantity"] += sl.quantity
        quantities[did]["source"].append("sale")

    for room in job.rooms.prefetch_related("devices__device").all():
        for rd in room.devices.filter(confirmed=True):
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

    grouped = {s.value: [] for s in ACTIVE_STAGES}
    archive = []
    for job in jobs:
        card = _card(job, backend_check_totals)
        if job.status in {s.value for s in ARCHIVE_STAGES}:
            archive.append(card)
        elif job.status in grouped:
            grouped[job.status].append(card)
        # Any unrecognized status: skip — shouldn't happen.

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
    })
