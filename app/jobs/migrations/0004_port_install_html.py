# Generated as part of Weeks 5-6 Phase 2: parse internal/install.html (S11)
# and create the "backend-install" v1 checklist template.
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from django.db import migrations


INSTALL_HTML = (
    Path(__file__).resolve().parents[3] / "internal" / "install.html"
)


def _step_title(title_el):
    # Title may include a trailing <span class="deferred">…</span>.
    # Stitch each direct text fragment together with an em-dash so the
    # badge text isn't lost when we flatten to a plain string.
    parts = []
    for node in title_el.children:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                parts.append(text)
        else:
            text = node.get_text(strip=True)
            if text:
                parts.append(text)
    if not parts:
        return "Untitled"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} — {' '.join(parts[1:])}"


def _check_body(li_tag):
    # The <li> wraps: <input> + <span class="inst-num">N</span> + <div>body</div>.
    # We only want the inner HTML of that <div>.
    div = li_tag.find("div", recursive=False)
    if not div:
        return ""
    return div.decode_contents().strip()


def _content_html(tag):
    # Outer HTML of a content block, with interactive widgets stripped:
    # "Copy" buttons in code blocks, onclick attributes anywhere.
    for btn in tag.find_all("button"):
        btn.decompose()
    for el in tag.find_all(attrs={"onclick": True}):
        del el.attrs["onclick"]
    return str(tag).strip()


def _flatten_spacing_wrappers(section):
    # Some steps wrap their <ol class="instructions"> or .capture-block inside
    # an unnamed <div style="margin-top: …"> just for CSS spacing. Unwrap those
    # so the structured elements become direct children of the section.
    while True:
        target = next(
            (
                d
                for d in section.find_all("div", recursive=False)
                if not d.get("class")
            ),
            None,
        )
        if target is None:
            return
        target.unwrap()


def _capture_rows(block_tag):
    for row in block_tag.find_all(class_="capture-row"):
        label_el = row.find(class_="capture-label")
        input_el = row.find("input", class_="capture-input")
        if not (label_el and input_el):
            continue
        raw_id = input_el.get("id", "")
        key = raw_id.removeprefix("cap_") if raw_id else ""
        if not key:
            # Fall back to slugified label so we never produce a blank key.
            key = (
                label_el.get_text(strip=True)
                .lower()
                .replace(" ", "_")
                .replace(".", "")
            )
        yield {
            "key": key,
            "label": label_el.get_text(strip=True),
            "placeholder": input_el.get("placeholder", ""),
        }


def port_install_html(apps, schema_editor):
    ChecklistTemplate = apps.get_model("jobs", "ChecklistTemplate")
    ChecklistStep = apps.get_model("jobs", "ChecklistStep")
    ChecklistItem = apps.get_model("jobs", "ChecklistItem")

    if not INSTALL_HTML.exists():
        raise RuntimeError(
            f"Cannot port checklist: install.html not found at {INSTALL_HTML}"
        )

    soup = BeautifulSoup(INSTALL_HTML.read_text(encoding="utf-8"), "html.parser")

    template = ChecklistTemplate.objects.create(
        slug="backend-install",
        version=1,
        title="Backend OS & Shop Prep",
        changelog="Initial port of internal/install.html (S11).",
    )

    for step_order, section in enumerate(
        soup.select("section.step-section"), start=1
    ):
        _flatten_spacing_wrappers(section)
        title_el = section.select_one(".step-title")
        title = _step_title(title_el) if title_el else f"Step {step_order}"
        step = ChecklistStep.objects.create(
            template=template, order=step_order, title=title,
        )

        item_order = 0
        for child in section.children:
            if isinstance(child, NavigableString):
                continue
            classes = set(child.get("class") or [])

            if "step-header" in classes:
                continue

            if child.name == "ol" and "instructions" in classes:
                for li in child.find_all("li", recursive=False):
                    item_order += 1
                    ChecklistItem.objects.create(
                        step=step,
                        order=item_order,
                        kind="check",
                        body_md=_check_body(li),
                    )
                continue

            if "capture-block" in classes:
                for row in _capture_rows(child):
                    item_order += 1
                    ChecklistItem.objects.create(
                        step=step,
                        order=item_order,
                        kind="capture",
                        capture_key=row["key"],
                        capture_label=row["label"],
                        capture_placeholder=row["placeholder"],
                    )
                continue

            body = _content_html(child)
            if body:
                item_order += 1
                ChecklistItem.objects.create(
                    step=step,
                    order=item_order,
                    kind="content",
                    body_md=body,
                )


def unport_install_html(apps, schema_editor):
    ChecklistTemplate = apps.get_model("jobs", "ChecklistTemplate")
    ChecklistTemplate.objects.filter(slug="backend-install", version=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0003_item_kinds_and_captures"),
    ]
    operations = [
        migrations.RunPython(port_install_html, unport_install_html),
    ]
