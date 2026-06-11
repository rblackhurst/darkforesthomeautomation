import json

from django import forms


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

    # ── Custom integrations / automations ─────────────────────────────────
    custom_integrations = forms.CharField(
        required=False,
        label="Custom integrations",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder":
            "List any existing devices the customer wants to integrate into Home Assistant "
            "(e.g. existing smart locks, cameras, sensors). Note: most cloud-only devices "
            "(Google Nest, Ring, Ecobee, Philips Hue cloud, etc.) cannot be integrated — "
            "we can investigate but cannot promise compatibility unless they are part of "
            "our regular offering."}),
    )
    custom_automations = forms.CharField(
        required=False,
        label="Custom automations",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder":
            "Describe any custom automation workflows the customer has requested "
            "beyond the standard package (e.g. 'lights off when last person leaves', "
            "'water shutoff when leak sensor triggers')."}),
    )

    # ── Service plan ──────────────────────────────────────────────────────
    service_plan_tier = forms.ChoiceField(
        required=False,
        label="Service plan",
        choices=[
            ('none', "No Service Plan"),
            ('tier1', "Basic ($29/mo — uptime checks + low-battery alerts)"),
            ('tier2', "Standard ($49/mo — Basic + updates + automation tweaks)"),
            ('tier3', "Premium ($79/mo — Standard + priority response + annual visit)"),
        ],
        initial='none',
        help_text="The uptime service plan the customer is signing up for.",
    )

    # ── Package + devices (sent as JSON by the JS layer) ──────────────────
    package_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    devices_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
        help_text="JSON array: [{device_id, quantity, notes}]",
    )

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
