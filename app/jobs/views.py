import json

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

    template = bi.template
    steps = list(template.steps.prefetch_related("items").all())
    item_states = {s.item_id: s for s in bi.item_states.all()}
    captures = {c.key: c.value for c in bi.captures.all()}

    rendered_steps = []
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
            entries.append(entry)
        rendered_steps.append({
            "step": step,
            "entries": entries,
            "check_done": check_done,
            "check_total": check_total,
        })

    return render(request, "jobs/backend_install.html", {
        "job": job,
        "backend_install": bi,
        "template": template,
        "steps": rendered_steps,
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
