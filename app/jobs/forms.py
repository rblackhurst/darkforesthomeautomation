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
    package_summary = forms.CharField(
        required=False,
        label="Package summary",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder":
            "e.g. Standard HA package — NUC + 6× Zigbee sensors + doorbell camera"}),
        help_text="Brief description of what was sold. Editable later.",
    )
    notes = forms.CharField(
        required=False,
        label="Internal notes",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder":
            "Anything else to know before the install (access codes, pets, …)"}),
    )

    def clean_invoice_number(self):
        val = self.cleaned_data["invoice_number"].strip()
        if Job.objects.filter(invoice_number=val).exists():
            raise forms.ValidationError(
                f"Job #{val} already exists. Use a different invoice number."
            )
        return val
