import json

from django import forms

from .models import Job


class SalesForm(forms.Form):
    # ── Customer ─────────────────────────────────────────────────────────
    first_name = forms.CharField(max_length=100, label="First name")
    last_name = forms.CharField(max_length=100, label="Last name")
    email = forms.EmailField(label="Email")
    phone = forms.CharField(
        max_length=40, required=False, label="Phone",
        help_text="Optional but useful for day-of coordination.",
    )

    # ── Job ───────────────────────────────────────────────────────────────
    invoice_number = forms.CharField(
        max_length=40,
        label="Invoice number",
        help_text="Must be unique — this becomes the permanent job ID.",
    )
    sold_on = forms.DateField(
        label="Sale date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    install_date = forms.DateField(
        required=False,
        label="Scheduled install date",
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Leave blank if not scheduled yet.",
    )
    notes = forms.CharField(
        required=False,
        label="Internal notes",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder":
            "Anything else to know before the install (access codes, pets, …)"}),
    )

    # ── Package + devices (sent as JSON by the JS layer) ──────────────────
    package_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    devices_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
        help_text="JSON array: [{device_id, quantity, notes}]",
    )

    def clean_invoice_number(self):
        val = self.cleaned_data["invoice_number"].strip()
        if Job.objects.filter(invoice_number=val).exists():
            raise forms.ValidationError(
                f"Job #{val} already exists. Use a different invoice number."
            )
        return val

    def clean_devices_json(self):
        raw = self.cleaned_data.get("devices_json", "").strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise forms.ValidationError("Device list is malformed.")
        if not isinstance(data, list):
            raise forms.ValidationError("Device list must be a JSON array.")
        cleaned = []
        for row in data:
            try:
                device_id = int(row["device_id"])
                quantity = max(1, int(row.get("quantity", 1)))
                notes = str(row.get("notes", ""))[:200]
                cleaned.append({"device_id": device_id, "quantity": quantity, "notes": notes})
            except (KeyError, ValueError, TypeError):
                raise forms.ValidationError("One or more device rows are malformed.")
        return cleaned
