import json
import secrets
import string

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from .models import (
    BackendInstall,
    BackendInstallCapture,
    BackendInstallItemState,
    ChecklistItem,
    ChecklistTemplate,
    Job,
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
