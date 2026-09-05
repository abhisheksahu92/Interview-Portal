"""Staffing back-office models: contractors, engagements, timesheets, money.

The shape is pinned by ARCHITECTURE.md "Phase 4 → contracting/". Everything
tenant-scoped hangs off ``core.Company`` and is filtered with ``for_company``.

Reuse notes:

* ``Contractor`` mixes in :class:`core.tokens.TokenMixin`, so a contractor's
  self-service timesheet link gets the same generate/expire/revoke/rotate
  plumbing as invitations and client-portal links.
* Bank details are stored in :class:`integrations.models.EncryptedJSONField`,
  i.e. a Fernet token, so a database dump does not leak account numbers.
* GST maths and financial-year labelling come from :mod:`billing.invoicing`.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils import timezone

from contracting.validators import validate_document_file
from core.tokens import TokenMixin
from integrations.models import EncryptedJSONField

TWO = Decimal("0.01")


def money(value):
    """Round ``value`` to paise, half-up (never bankers' rounding on money)."""
    return Decimal(value or 0).quantize(TWO, rounding=ROUND_HALF_UP)


class CompanyQuerySet(models.QuerySet):
    """Shared tenant filter for rows carrying a direct ``company`` FK."""

    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)


class ClientBillingProfile(models.Model):
    """GST/billing details for one :class:`clients.Client`.

    Lives here rather than on ``clients.Client`` because the clients app is
    owned by another agent: this app must not widen their model.
    """

    client = models.OneToOneField(
        "clients.Client", on_delete=models.CASCADE, related_name="billing_profile"
    )
    gstin = models.CharField(max_length=20, blank=True)
    state_code = models.CharField(
        max_length=2,
        blank=True,
        help_text="Two-digit GST state code of the client's place of supply, e.g. 27.",
    )
    billing_email = models.EmailField(blank=True)
    billing_address = models.TextField(blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["client__name"]

    def __str__(self):
        return f"Billing profile for {self.client}"

    @property
    def company(self):
        return self.client.company

    @classmethod
    def for_client(cls, client):
        """The profile for ``client``, or an unsaved blank one."""
        profile = cls.objects.filter(client=client).first()
        return profile or cls(client=client)


class Contractor(TokenMixin, models.Model):
    """A placed contractor on the staffing firm's books."""

    ONBOARDING = "ONBOARDING"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    STATUS_CHOICES = [
        (ONBOARDING, "Onboarding"),
        (ACTIVE, "Active"),
        (ENDED, "Ended"),
    ]

    #: Self-service timesheet links do not expire; revoke or rotate instead.
    EXPIRY_DAYS = None

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="contractors"
    )
    candidate = models.ForeignKey(
        "jobs.CandidateProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contractor_records",
    )
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=25, blank=True)
    pan = models.CharField(max_length=10, blank=True)
    uan = models.CharField(max_length=20, blank=True)
    employee_id = models.CharField(
        max_length=40, blank=True, help_text="Payroll id used by your HRMS import."
    )
    #: {"account_number": ..., "ifsc": ..., "bank_name": ..., "holder": ...}
    bank = EncryptedJSONField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=ONBOARDING)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def link_purpose(self):
        return "Timesheet link"

    @property
    def bank_account(self):
        return (self.bank or {}).get("account_number", "")

    @property
    def ifsc(self):
        return (self.bank or {}).get("ifsc", "")

    @property
    def payroll_id(self):
        """What the HRMS CSV uses as ``employee_id``."""
        return self.employee_id or f"C{self.pk:05d}"

    def document_kinds(self):
        return {doc.kind for doc in self.documents.all()}

    def verified_kinds(self):
        return {doc.kind for doc in self.documents.all() if doc.verified_at}


class Engagement(models.Model):
    """One contractor placed with one client at a bill rate and a pay rate."""

    HOUR = "HOUR"
    DAY = "DAY"
    MONTH = "MONTH"
    RATE_UNIT_CHOICES = [(HOUR, "Per hour"), (DAY, "Per day"), (MONTH, "Per month")]

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    STATUS_CHOICES = [(DRAFT, "Draft"), (ACTIVE, "Active"), (ENDED, "Ended")]

    DEFAULT_TDS_PERCENT = Decimal("10")

    contractor = models.ForeignKey(
        Contractor, on_delete=models.CASCADE, related_name="engagements"
    )
    client = models.ForeignKey(
        "clients.Client", on_delete=models.PROTECT, related_name="engagements"
    )
    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="engagements",
    )
    role_title = models.CharField(max_length=200)
    start = models.DateField()
    end = models.DateField(null=True, blank=True)
    bill_rate_inr = models.DecimalField(max_digits=12, decimal_places=2)
    pay_rate_inr = models.DecimalField(max_digits=12, decimal_places=2)
    rate_unit = models.CharField(max_length=6, choices=RATE_UNIT_CHOICES, default=HOUR)
    tds_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=DEFAULT_TDS_PERCENT,
        help_text="Withheld from the contractor's gross (194J/194C).",
    )
    po_number = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start", "contractor__name"]

    def __str__(self):
        return f"{self.contractor.name} @ {self.client.name}"

    @property
    def company(self):
        return self.contractor.company

    @property
    def margin_per_unit(self):
        return money(self.bill_rate_inr) - money(self.pay_rate_inr)

    @property
    def margin_percent(self):
        bill = money(self.bill_rate_inr)
        if not bill:
            return Decimal("0.00")
        return money(self.margin_per_unit * 100 / bill)

    @property
    def is_open(self):
        return self.status == self.ACTIVE and (
            self.end is None or self.end >= timezone.localdate()
        )


class OnboardingDocument(models.Model):
    """One uploaded onboarding artefact for a contractor."""

    PAN = "PAN"
    AADHAAR = "AADHAAR"
    OFFER = "OFFER"
    NDA = "NDA"
    OTHER = "OTHER"
    KIND_CHOICES = [
        (PAN, "PAN card"),
        (AADHAAR, "Aadhaar"),
        (OFFER, "Signed offer"),
        (NDA, "NDA"),
        (OTHER, "Other"),
    ]
    #: Kinds the onboarding checklist insists on before a contractor goes ACTIVE.
    REQUIRED_KINDS = (PAN, AADHAAR, OFFER, NDA)

    contractor = models.ForeignKey(
        Contractor, on_delete=models.CASCADE, related_name="documents"
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=OTHER)
    file = models.FileField(
        upload_to="contracting/documents/", validators=[validate_document_file]
    )
    uploaded_by = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.contractor.name}"

    @property
    def company(self):
        return self.contractor.company

    @property
    def is_verified(self):
        return self.verified_at is not None

    def mark_verified(self):
        if self.verified_at is None:
            self.verified_at = timezone.now()
            self.save(update_fields=["verified_at"])
        return self


class TimesheetQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(engagement__contractor__company=company)

    def for_client(self, client):
        return self.filter(engagement__client=client)

    def awaiting_approval(self):
        return self.filter(status=Timesheet.SUBMITTED)

    def billable(self):
        return self.filter(status=Timesheet.APPROVED)


class Timesheet(models.Model):
    """A period of work on one engagement, moving DRAFT → SUBMITTED → APPROVED.

    ``entries`` is ``[{"date": "2026-04-01", "hours": 8, "note": ""}, ...]``;
    ``total_hours`` is always recomputed from it on save so the stored total
    cannot drift from the grid the contractor filled in.
    """

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INVOICED = "INVOICED"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SUBMITTED, "Submitted"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
        (INVOICED, "Invoiced"),
    ]
    #: The only legal moves; anything else raises ``InvalidTransition``.
    TRANSITIONS = {
        DRAFT: {SUBMITTED},
        SUBMITTED: {APPROVED, REJECTED},
        REJECTED: {SUBMITTED},
        APPROVED: {INVOICED, REJECTED},
        INVOICED: set(),
    }
    #: States the contractor may still edit the grid in.
    EDITABLE_STATES = (DRAFT, REJECTED)

    engagement = models.ForeignKey(
        Engagement, on_delete=models.CASCADE, related_name="timesheets"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    entries = models.JSONField(default=list, blank=True)
    total_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by_user = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_by_access = models.ForeignKey(
        "clients.ClientAccess",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    client_note = models.TextField(blank=True)
    client_invoice = models.ForeignKey(
        "contracting.ClientInvoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timesheets",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TimesheetQuerySet.as_manager()

    class Meta:
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "period_start"], name="uniq_timesheet_period"
            )
        ]

    def __str__(self):
        return f"{self.engagement} {self.period_start}–{self.period_end}"

    def save(self, *args, **kwargs):
        self.entries = normalise_entries(self.entries)
        self.total_hours = sum_hours(self.entries)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = sorted(set(update_fields) | {"entries", "total_hours"})
        super().save(*args, **kwargs)

    @property
    def company(self):
        return self.engagement.contractor.company

    @property
    def client(self):
        return self.engagement.client

    @property
    def days_worked(self):
        """Distinct dates with any hours on them — the DAY/MONTH rate driver."""
        return len({e["date"] for e in (self.entries or []) if Decimal(str(e.get("hours") or 0)) > 0})

    @property
    def is_editable(self):
        return self.status in self.EDITABLE_STATES

    @property
    def approver_label(self):
        if self.approved_by_access_id:
            return self.approved_by_access.email
        if self.approved_by_user_id:
            return self.approved_by_user.get_full_name() or self.approved_by_user.email
        return ""

    def can_transition_to(self, status):
        return status in self.TRANSITIONS.get(self.status, set())


class ClientInvoiceCounter(models.Model):
    """Per-company, per-financial-year invoice sequence.

    Numbers are allocated by locking this row inside a transaction, exactly
    like :class:`billing.models.InvoiceCounter` — never by scanning existing
    numbers, which races.
    """

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="client_invoice_counters"
    )
    fy = models.CharField(max_length=10)
    last_seq = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company_id", "fy"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "fy"], name="uniq_client_invoice_counter"
            )
        ]

    def __str__(self):
        return f"{self.company_id}/{self.fy} @ {self.last_seq}"


class ClientInvoice(models.Model):
    """A GST invoice raised on a client for a period of approved timesheets."""

    DRAFT = "DRAFT"
    SENT = "SENT"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SENT, "Sent"),
        (PAID, "Paid"),
        (OVERDUE, "Overdue"),
    ]
    GST_RATE = Decimal("18.00")

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="client_invoices"
    )
    client = models.ForeignKey(
        "clients.Client", on_delete=models.PROTECT, related_name="invoices"
    )
    number = models.CharField(max_length=40, unique=True)
    fy = models.CharField(max_length=10, blank=True)
    period_start = models.DateField()
    period_end = models.DateField()
    #: [{"label", "qty", "unit_inr", "total_inr", "engagement", "timesheet"}]
    line_items = models.JSONField(default=list, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=GST_RATE)
    cgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gstin = models.CharField(max_length=20, blank=True)
    place_of_supply = models.CharField(max_length=2, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=DRAFT)
    due_at = models.DateField(null=True, blank=True)
    pdf = models.FileField(upload_to="contracting/invoices/", blank=True)
    issued_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyQuerySet.as_manager()

    class Meta:
        ordering = ["-issued_at", "-id"]

    def __str__(self):
        return self.number

    @property
    def tax_total(self):
        return money(self.cgst) + money(self.sgst) + money(self.igst)

    @property
    def is_intra_state(self):
        return bool(self.cgst or self.sgst)

    @property
    def is_paid(self):
        return self.status == self.PAID

    @property
    def is_overdue(self):
        if self.is_paid or self.due_at is None:
            return False
        return self.due_at < timezone.localdate()

    @property
    def days_outstanding(self):
        """Age in days used by the DSO metric."""
        end = self.paid_at or timezone.now()
        return max((end - self.issued_at).days, 0)

    @property
    def status_kind(self):
        """Badge modifier for ``.ip-badge--*``."""
        if self.is_paid:
            return "success"
        if self.is_overdue or self.status == self.OVERDUE:
            return "danger"
        return "accent" if self.status == self.SENT else "neutral"


class PayrollRun(models.Model):
    """One month's contractor payout computation for a company."""

    DRAFT = "DRAFT"
    FINAL = "FINAL"
    STATUS_CHOICES = [(DRAFT, "Draft"), (FINAL, "Final")]

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="payroll_runs"
    )
    month = models.DateField(help_text="Any date inside the payroll month; stored as the 1st.")
    #: [{"contractor_id", "employee_id", "name", "pan", "days", "hours",
    #:   "gross", "tds", "net", "bank_account", "ifsc"}]
    rows = models.JSONField(default=list, blank=True)
    gross_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tds_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    csv = models.FileField(upload_to="contracting/payroll/", blank=True)
    status = models.CharField(max_length=6, choices=STATUS_CHOICES, default=DRAFT)
    created_by = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyQuerySet.as_manager()

    class Meta:
        ordering = ["-month"]
        constraints = [
            models.UniqueConstraint(fields=["company", "month"], name="uniq_payroll_run_month")
        ]

    def __str__(self):
        return f"Payroll {self.month:%b %Y} · {self.company_id}"

    @property
    def headcount(self):
        return len(self.rows or [])

    @property
    def label(self):
        return f"{self.month:%B %Y}"


def normalise_entries(entries):
    """Coerce a submitted grid into ``[{date, hours, note}]``, dropping junk."""
    cleaned = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        date = str(entry.get("date") or "").strip()
        if not date:
            continue
        try:
            hours = Decimal(str(entry.get("hours") or 0))
        except (ArithmeticError, ValueError, TypeError):
            hours = Decimal("0")
        if hours < 0:
            hours = Decimal("0")
        cleaned.append(
            {
                "date": date,
                "hours": float(hours.quantize(TWO, rounding=ROUND_HALF_UP)),
                "note": str(entry.get("note") or "")[:200],
            }
        )
    cleaned.sort(key=lambda e: e["date"])
    return cleaned


def sum_hours(entries):
    total = sum((Decimal(str(e.get("hours") or 0)) for e in entries or []), Decimal("0"))
    return total.quantize(TWO, rounding=ROUND_HALF_UP)
