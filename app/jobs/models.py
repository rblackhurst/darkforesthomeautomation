from django.conf import settings
from django.db import models


def _fmt_order(value):
    # Render a Decimal sort-order as a plain int when it has no fractional
    # part, so admin labels show "3" instead of "3.000".
    if value is None:
        return ""
    if value == value.to_integral_value():
        return str(int(value))
    return str(value.normalize())


class Customer(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=40, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    stripe_customer_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text="Stripe Customer ID (cus_...). Set on first Stripe interaction. Never set manually.",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["last_name"])]

    def __str__(self):
        return f"{self.last_name}, {self.first_name}"


class Job(models.Model):
    class Status(models.TextChoices):
        SOLD = "sold", "Sold"
        DEPOSIT_RECEIVED = "deposit_received", "Deposit Received"
        PRE_INSTALL = "pre_install", "Pre-install"
        BACKEND = "backend", "Backend prep"
        PAIRING = "pairing", "Pairing"
        AUTOMATION = "automation", "Automation config"
        ONSITE = "onsite", "On-site install"
        WALKTHROUGH = "walkthrough", "Walkthrough"
        FINAL_PAID = "final_paid", "Final Paid"
        COMPLETE = "complete", "Complete"
        CANCELLED = "cancelled", "Cancelled"

    class ServiceTier(models.TextChoices):
        NONE = 'none', 'No Service Plan'
        BASIC = 'tier1', 'Basic'
        STANDARD = 'tier2', 'Standard'
        PREMIUM = 'tier3', 'Premium'

    invoice_number = models.CharField(max_length=40, primary_key=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="jobs")
    package = models.ForeignKey(
        "Package",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs",
        help_text="Install package selected at sale time.",
    )
    service_plan_tier = models.CharField(
        max_length=10,
        choices=ServiceTier.choices,
        default=ServiceTier.NONE,
        blank=True,
        help_text="Uptime service plan the customer signed up for "
                  "(uptime checks, updates, battery kits, on-site visits).",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SOLD)
    sold_on = models.DateField(null=True, blank=True)
    install_date = models.DateField(null=True, blank=True)
    package_summary = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    # Custom integrations / automations captured at sale + pre-install
    custom_integrations = models.TextField(
        blank=True,
        help_text="Existing devices the customer wants integrated (e.g. smart locks, cameras). "
                  "Note: most cloud-only devices (Google Nest, etc.) cannot be integrated.",
    )
    custom_automations = models.TextField(
        blank=True,
        help_text="Custom automation requests beyond the standard package.",
    )
    # Finalization + payment
    display_invoice_number = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        unique=True,
        help_text="System-generated customer-facing invoice code "
                  "(YYMMDD + rooms + adhoc + seq, 13 chars). "
                  "Set when the pre-install walkthrough is finalized.",
    )
    finalized_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the sale was finalized and the invoice number was generated.",
    )
    payment_override = models.BooleanField(
        default=False,
        help_text="Skip the automatic payment email — handle payment manually.",
    )
    payment_override_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Custom total override for testing / reduced-price installs.",
    )
    payment_received = models.BooleanField(default=False)
    payment_received_at = models.DateTimeField(null=True, blank=True)

    # ── Stripe: Quote ──────────────────────────────────────────────────────────
    stripe_quote_id = models.CharField(max_length=255, null=True, blank=True)

    # ── Stripe: Deposit Invoice (Invoice #1 — 50% of accepted quote) ───────────
    stripe_deposit_invoice_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_deposit_invoice_url = models.URLField(null=True, blank=True)
    deposit_paid = models.BooleanField(default=False)

    # ── Stripe: Final Invoice (Invoice #2 — remaining balance + additions) ─────
    stripe_final_invoice_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_final_invoice_url = models.URLField(null=True, blank=True)
    final_paid = models.BooleanField(default=False)

    # ── Stripe: Subscription ───────────────────────────────────────────────────
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    subscription_status = models.CharField(max_length=50, null=True, blank=True)
    # Set before sending final invoice; webhook clears it after creating the subscription.
    pending_subscription_price_id = models.CharField(max_length=255, blank=True, default='')

    # ── Stripe: Payment Health ─────────────────────────────────────────────────
    payment_failed = models.BooleanField(default=False)
    payment_failed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-install_date", "-created_at"]
        indexes = [
            models.Index(fields=["install_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        ref = self.display_invoice_number or self.invoice_number
        return f"Job {ref} — {self.customer}"

    @property
    def invoice_label(self):
        """Human-readable invoice reference for UI and emails."""
        return self.display_invoice_number or "Pending"

    @property
    def is_locked(self):
        return (
            hasattr(self, "walkthrough_signoff")
            and self.walkthrough_signoff.signed_at is not None
        )


class InstallRecord(models.Model):
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def is_complete(self):
        return self.completed_at is not None


class BackendInstall(InstallRecord):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="backend_install")
    template = models.ForeignKey(
        "ChecklistTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="backend_installs",
        help_text="Snapshot reference: this BackendInstall renders against this exact "
                  "template version, even if a newer version is published later.",
    )

    def __str__(self):
        return f"BackendInstall for {self.job_id}"


class PairingSheet(InstallRecord):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="pairing_sheet")
    locked = models.BooleanField(
        default=False,
        help_text="Locked once pairing is complete. Unlocking is audit-logged after walkthrough.",
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self):
        return f"PairingSheet for {self.job_id}"


class AutomationConfig(InstallRecord):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="automation_config")
    blueprints = models.JSONField(default=list, blank=True)
    custom_yaml = models.TextField(blank=True)

    def __str__(self):
        return f"AutomationConfig for {self.job_id}"


class OnsiteInstall(InstallRecord):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="onsite_install")
    vlan_changes = models.TextField(blank=True)
    tailscale_account = models.CharField(max_length=200, blank=True)
    remote_monitoring = models.TextField(blank=True)

    def __str__(self):
        return f"OnsiteInstall for {self.job_id}"


class WalkthroughSignoff(models.Model):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="walkthrough_signoff")
    signed_at = models.DateTimeField(null=True, blank=True)
    signed_by_name = models.CharField(max_length=200, blank=True)
    signed_by_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="signoffs_witnessed",
    )
    customer_acknowledgement = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Walkthrough for {self.job_id}"


class AuditLogEntry(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="audit_entries")
    section = models.CharField(max_length=80)
    field = models.CharField(max_length=120)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_changes",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        indexes = [models.Index(fields=["job", "-changed_at"])]

    def __str__(self):
        return f"{self.job_id}.{self.section}.{self.field} @ {self.changed_at:%Y-%m-%d}"


class TroubleRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="trouble_requests")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trouble_requests",
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    submitted_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.subject} ({self.job_id})"


class CredentialBundle(models.Model):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="credentials")
    # v1 stores payload as plaintext JSON. Encryption + one-time encrypted
    # export ship in Weeks 11–12 (PLANNING.md §6). Until then, treat as
    # sensitive: admin access is gated on staff role.
    payload = models.JSONField(default=dict, blank=True)
    last_revealed_at = models.DateTimeField(null=True, blank=True)
    last_exported_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Credentials for {self.job_id}"


class ChecklistTemplate(models.Model):
    # A versioned, named checklist (e.g. "backend-install" v1, v2 …).
    # Each install record snapshots a specific template; revising the
    # template later does not change what an in-progress install renders.
    slug = models.SlugField(max_length=60)
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    changelog = models.TextField(
        blank=True,
        help_text="What changed in this version vs. the previous one.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slug", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["slug", "version"], name="unique_template_version"),
        ]

    def __str__(self):
        return f"{self.title} (v{self.version})"

    @classmethod
    def current_for(cls, slug):
        return cls.objects.filter(slug=slug).order_by("-version").first()


class ChecklistStep(models.Model):
    template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.CASCADE, related_name="steps",
    )
    order = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        help_text="Sort order within the template. To insert a new step "
                  "between existing ones, use a fractional value (e.g. 2.5 "
                  "to land between 2 and 3); on save the admin renumbers "
                  "every step to clean sequential integers.",
    )
    title = models.CharField(max_length=200)
    intro_md = models.TextField(
        blank=True,
        help_text="Optional Markdown intro shown above the items in this step.",
    )

    class Meta:
        ordering = ["template", "order", "id"]

    def __str__(self):
        return f"{self.template.slug} v{self.template.version} · {_fmt_order(self.order)}. {self.title}"


class ChecklistItem(models.Model):
    # An ordered element inside a step. Kind drives how it renders:
    #   check   — checkbox + body (installer ticks it off)
    #   content — freeform body, no checkbox (prose, code blocks, callouts, nav paths)
    #   capture — labeled form input that records per-install data
    class Kind(models.TextChoices):
        CHECK = "check", "Checkbox item"
        CONTENT = "content", "Content block"
        CAPTURE = "capture", "Capture input"

    step = models.ForeignKey(ChecklistStep, on_delete=models.CASCADE, related_name="items")
    order = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        help_text="Sort order within the step. To insert a new item "
                  "between existing ones, use a fractional value (e.g. 2.5 "
                  "to land between 2 and 3); on save the admin renumbers "
                  "every item to clean sequential integers.",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CHECK)
    body_md = models.TextField(
        blank=True,
        help_text="Markdown/HTML body. For check items: the instruction. "
                  "For content items: the rendered block (prose, code, callout, nav path). "
                  "For capture items: optional helper text shown next to the input.",
    )
    capture_key = models.SlugField(
        max_length=60,
        blank=True,
        help_text="Slug key for capture items (e.g. 'hostname', 'nuc_static_ip'). "
                  "Per-install values are stored in BackendInstallCapture keyed by this slug.",
    )
    capture_label = models.CharField(
        max_length=120,
        blank=True,
        help_text="Label shown next to the capture input (e.g. 'HAOS Hostname').",
    )
    capture_placeholder = models.CharField(
        max_length=120,
        blank=True,
        help_text="Placeholder text for the capture input (e.g. 'e.g. HASmitr').",
    )

    class Meta:
        ordering = ["step", "order", "id"]

    def __str__(self):
        snippet = (self.body_md[:60] + "…") if len(self.body_md) > 60 else self.body_md
        label = self.capture_label or snippet or f"[{self.kind}]"
        return f"{_fmt_order(self.step.order)}.{_fmt_order(self.order)} ({self.kind}) {label}"


class BackendInstallItemState(models.Model):
    backend_install = models.ForeignKey(
        BackendInstall, on_delete=models.CASCADE, related_name="item_states",
    )
    item = models.ForeignKey(ChecklistItem, on_delete=models.PROTECT, related_name="+")
    checked = models.BooleanField(default=False)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    checked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(
        blank=True,
        help_text="Per-item installer notes (e.g. 'used 16GB drive — none in stock').",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["backend_install", "item"], name="unique_backend_item_state",
            ),
        ]

    def __str__(self):
        return f"{self.backend_install.job_id} · item {self.item_id} · {'✓' if self.checked else '·'}"


class BackendInstallCapture(models.Model):
    # Per-install values for ChecklistItem kind=capture. Generic key/value
    # so install.html can grow new capture fields without migrations.
    # Once any of these values stabilize into "this is always a credential"
    # or "this is always a network address," promote them to typed fields
    # on BackendInstall or rows in CredentialBundle.
    backend_install = models.ForeignKey(
        BackendInstall, on_delete=models.CASCADE, related_name="captures",
    )
    key = models.SlugField(max_length=60)
    value = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["backend_install", "key"], name="unique_backend_capture_key",
            ),
        ]

    def __str__(self):
        return f"{self.backend_install.job_id} · {self.key}"


class CatalogDevice(models.Model):
    class DeviceType(models.TextChoices):
        NUC = "nuc", "NUC / Server"
        SWITCH = "switch", "Network switch"
        ACCESS_POINT = "ap", "Access point"
        RELAY = "relay", "Smart relay"
        PLUG = "plug", "Smart plug"
        SENSOR = "sensor", "Sensor"
        CAMERA = "camera", "Camera"
        LOCK = "lock", "Smart lock"
        THERMOSTAT = "thermostat", "Thermostat"
        HUB = "hub", "Hub / bridge"
        KIT = "kit", "Room / install kit"
        OTHER = "other", "Other"

    device_type = models.CharField(max_length=20, choices=DeviceType.choices)
    model_name = models.CharField(max_length=200)
    supplier = models.CharField(max_length=200, blank=True)
    supplier_sku = models.CharField(max_length=100, blank=True)
    purchase_url = models.URLField(blank=True)
    default_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    function_slug = models.SlugField(
        max_length=40, blank=True,
        help_text="Function token used by the pairing sheet to generate HA entity names "
                  "(e.g. 'door', 'presence', 'light', 'tilt'). The pairing sheet formula "
                  "produces '{room_slug}_{device_kind}_{function_slug}'. Leave blank for "
                  "devices that don't get a name (NUC, UPS, kits).",
    )
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["device_type", "model_name"]

    def __str__(self):
        return f"{self.get_device_type_display()} — {self.model_name}"


class PreInstallChecklist(InstallRecord):
    job = models.OneToOneField(
        Job, on_delete=models.CASCADE, related_name="pre_install_checklist",
    )
    template = models.ForeignKey(
        "ChecklistTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pre_install_checklists",
        help_text="Snapshot reference: this checklist renders against this exact "
                  "template version, even if a newer version is published later.",
    )
    invoice_sent = models.BooleanField(
        default=False,
        help_text="Checked once the payment quote / invoice has been confirmed sent to the customer.",
    )
    invoice_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"PreInstallChecklist for {self.job_id}"


class PreInstallItemState(models.Model):
    pre_install_checklist = models.ForeignKey(
        PreInstallChecklist, on_delete=models.CASCADE, related_name="item_states",
    )
    item = models.ForeignKey(ChecklistItem, on_delete=models.PROTECT, related_name="+")
    checked = models.BooleanField(default=False)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    checked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(
        blank=True,
        help_text="Per-item installer notes.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["pre_install_checklist", "item"],
                name="unique_pre_install_item_state",
            ),
        ]

    def __str__(self):
        tick = "✓" if self.checked else "·"
        return f"{self.pre_install_checklist.job_id} · item {self.item_id} · {tick}"


class PreInstallCapture(models.Model):
    pre_install_checklist = models.ForeignKey(
        PreInstallChecklist, on_delete=models.CASCADE, related_name="captures",
    )
    key = models.SlugField(max_length=60)
    value = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["pre_install_checklist", "key"],
                name="unique_pre_install_capture_key",
            ),
        ]

    def __str__(self):
        return f"{self.pre_install_checklist.job_id} · {self.key}"


# ── Packages & sale lines ─────────────────────────────────────────────────────

class Package(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Base sale price for this package.",
    )
    default_rooms = models.JSONField(
        null=True, blank=True,
        help_text='Rooms to auto-create when this package is selected at sale time. '
                  'List of objects: {"room_type": "bedroom", "custom_name": "Primary"}. '
                  'custom_name is optional.',
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PackageDevice(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="devices")
    device = models.ForeignKey(
        CatalogDevice, on_delete=models.PROTECT, related_name="package_lines",
    )
    quantity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["device__device_type", "device__model_name"]

    def __str__(self):
        return f"{self.package.name}: {self.quantity}× {self.device.model_name}"


class SaleLine(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="sale_lines")
    device = models.ForeignKey(
        CatalogDevice, on_delete=models.PROTECT, related_name="sale_lines",
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Snapshot of the device cost at time of sale.",
    )
    notes = models.CharField(max_length=200, blank=True)
    confirmed_in_stock = models.BooleanField(default=False)
    from_package = models.BooleanField(
        default=False,
        help_text="True if this line was pre-filled from the selected package.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.job_id}: {self.quantity}× {self.device.model_name}"

    @property
    def line_total(self):
        if self.unit_cost is not None:
            return self.unit_cost * self.quantity
        return None


# ── Internal prep ─────────────────────────────────────────────────────────────

class InternalPrep(models.Model):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="internal_prep")
    github_username = models.CharField(max_length=100, blank=True)
    github_created = models.BooleanField(default=False)
    picklist_picked = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"InternalPrep for {self.job_id}"


# ── Room walkthrough ──────────────────────────────────────────────────────────

class Room(models.Model):
    class RoomType(models.TextChoices):
        LIVING_ROOM = "living_room", "Living room"
        KITCHEN = "kitchen", "Kitchen"
        DINING_ROOM = "dining_room", "Dining room"
        BEDROOM = "bedroom", "Bedroom"
        BATHROOM = "bathroom", "Bathroom"
        OFFICE = "office", "Office"
        GARAGE = "garage", "Garage"
        BASEMENT = "basement", "Basement"
        LAUNDRY = "laundry", "Laundry room"
        HALLWAY = "hallway", "Hallway"
        ENTRYWAY = "entryway", "Entryway"
        OUTDOOR = "outdoor", "Backyard / outdoor"
        OTHER = "other", "Other"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="rooms")
    room_type = models.CharField(max_length=20, choices=RoomType.choices)
    custom_name = models.CharField(
        max_length=100, blank=True,
        help_text="Optional label to distinguish this room from others of the same type "
                  "(e.g. 'Master', 'Kids', 'Grandma's').",
    )
    order = models.PositiveSmallIntegerField(default=0)
    from_package = models.BooleanField(
        default=False,
        help_text="True if this room was auto-created from the package default_rooms list. "
                  "Allows re-applying a package without losing manually-added rooms.",
    )

    class Meta:
        ordering = ["order", "id"]

    @property
    def display_label(self):
        base = self.get_room_type_display()
        return f"{base} — {self.custom_name}" if self.custom_name else base

    def __str__(self):
        return f"{self.job_id}: {self.display_label}"


class RoomDevice(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="devices")
    device = models.ForeignKey(
        CatalogDevice, on_delete=models.PROTECT, related_name="room_devices",
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    confirmed = models.BooleanField(
        default=False,
        help_text="Customer confirmed this device goes in this room.",
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.room}: {self.quantity}× {self.device.model_name}"


# ── Pairing sheet rows ────────────────────────────────────────────────────────

class PairingSheetDevice(models.Model):
    """One row per individual paired device on a job's pairing sheet.

    Generated from RoomDevice on first load of the pairing sheet: a RoomDevice
    with quantity=3 becomes three PairingSheetDevice rows. The HA entity name
    is pre-filled from the {room_slug}_{device_kind}_{function_slug} formula
    and remains editable until the pairing sheet is locked.
    """

    pairing_sheet = models.ForeignKey(
        PairingSheet, on_delete=models.CASCADE, related_name="device_rows",
    )
    room_device = models.ForeignKey(
        RoomDevice, on_delete=models.CASCADE, related_name="pairing_rows",
    )
    instance_index = models.PositiveSmallIntegerField(
        default=1,
        help_text="1-based index when a RoomDevice has quantity > 1. Used to disambiguate names.",
    )
    ha_name = models.CharField(
        max_length=120, blank=True,
        help_text="Home Assistant / Zigbee2MQTT friendly name. Editable by staff.",
    )
    paired = models.BooleanField(default=False)
    paired_at = models.DateTimeField(null=True, blank=True)
    paired_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["pairing_sheet", "room_device", "instance_index"],
                name="unique_pairing_row_per_instance",
            ),
        ]
        ordering = ["room_device__room__order", "room_device_id", "instance_index"]

    def __str__(self):
        return f"{self.pairing_sheet.job_id}: {self.ha_name or '(unnamed)'}"
