"""Background verification: resold check packages and the orders raised on them.

The money shape is deliberately simple and auditable:

* :class:`CheckPackage` carries both what the vendor charges us
  (``provider_cost_inr``) and what the tenant pays (``price_inr``). The
  difference is the platform's margin and is never shown to a tenant.
* :class:`VerificationOrder` **snapshots** both numbers at order time, so
  re-pricing a package tomorrow can never restate yesterday's invoice or
  yesterday's margin.
* The tenant is charged exactly once, at the moment the candidate consents,
  through :func:`billing.ledger.add_charge` with ``ref="bgv:<pk>"`` — an
  idempotency key, so a double submit cannot double bill.

The candidate's consent link reuses :class:`core.tokens.TokenMixin`, the same
plumbing behind invitations, client-portal links and contractor timesheets.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import models

from core.tokens import TokenMixin

TWO = Decimal("0.01")

#: Every check a package may contain, in report order.
CHECK_CODES = ("identity", "address", "employment", "education", "criminal")

CHECK_LABELS = {
    "identity": "Identity",
    "address": "Address",
    "employment": "Employment history",
    "education": "Education",
    "criminal": "Criminal record",
}


def money(value):
    """Round to paise, half-up — never bankers' rounding on money."""
    return Decimal(value or 0).quantize(TWO, rounding=ROUND_HALF_UP)


def check_label(code):
    return CHECK_LABELS.get(code, str(code).replace("_", " ").capitalize())


class CheckPackage(models.Model):
    """A bundle of checks resold at a fixed price. Global, not per tenant."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    provider_cost_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    checks = models.JSONField(default=list, blank=True)
    turnaround_days = models.PositiveSmallIntegerField(default=5)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["price_inr", "code"]

    def __str__(self):
        return self.name

    @property
    def margin_inr(self):
        return money(self.price_inr) - money(self.provider_cost_inr)

    @property
    def margin_percent(self):
        price = money(self.price_inr)
        if price <= 0:
            return Decimal("0.00")
        return money(self.margin_inr * 100 / price)

    @property
    def check_labels(self):
        return [check_label(code) for code in (self.checks or [])]


class VerificationOrderQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)

    def billable(self):
        """Orders that have actually been charged (consent given, not cancelled)."""
        return self.exclude(status=VerificationOrder.CANCELLED).exclude(charge_ref="")


class VerificationOrder(TokenMixin, models.Model):
    """One background check ordered on one candidate by one company."""

    DRAFT = "DRAFT"
    CONSENT_PENDING = "CONSENT_PENDING"
    SUBMITTED = "SUBMITTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (CONSENT_PENDING, "Awaiting consent"),
        (SUBMITTED, "Submitted"),
        (IN_PROGRESS, "In progress"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
        (CANCELLED, "Cancelled"),
    ]
    #: Statuses in which no money has moved and cancelling is free.
    PRE_CHARGE_STATUSES = (DRAFT, CONSENT_PENDING)
    OPEN_STATUSES = (DRAFT, CONSENT_PENDING, SUBMITTED, IN_PROGRESS)

    #: The consent link is good for a fortnight, like a team invitation.
    EXPIRY_DAYS = 14

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="verification_orders"
    )
    application = models.ForeignKey(
        "jobs.Application",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verification_orders",
    )
    candidate = models.ForeignKey(
        "jobs.CandidateProfile", on_delete=models.CASCADE, related_name="verification_orders"
    )
    package = models.ForeignKey(
        CheckPackage, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    #: Snapshots taken at order time; the package may be re-priced later.
    price_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    provider_cost_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    checks = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT)
    consent_given_at = models.DateTimeField(null=True, blank=True)
    consent_ip = models.GenericIPAddressField(null=True, blank=True)
    consent_name = models.CharField(max_length=150, blank=True)
    provider = models.CharField(max_length=40, blank=True)
    provider_ref = models.CharField(max_length=120, blank=True)
    result = models.JSONField(default=dict, blank=True)
    report_file = models.FileField(upload_to="bgv/reports/", blank=True)
    ordered_by = models.ForeignKey(
        "core.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verification_orders",
    )
    ordered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    #: The ``billing.BillingCharge.ref`` raised for this order; blank = unbilled.
    charge_ref = models.CharField(max_length=100, blank=True)

    objects = VerificationOrderQuerySet.as_manager()

    class Meta:
        ordering = ["-ordered_at", "-id"]

    def __str__(self):
        return f"BGV #{self.pk} — {self.candidate_name}"

    # -- display ----------------------------------------------------------- #

    @property
    def candidate_name(self):
        user = getattr(self.candidate, "user", None)
        full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
        return full or getattr(user, "email", "") or "Candidate"

    @property
    def candidate_email(self):
        return getattr(getattr(self.candidate, "user", None), "email", "")

    @property
    def job_title(self):
        return getattr(getattr(self.application, "job", None), "title", "")

    @property
    def status_kind(self):
        """Badge modifier used by the templates."""
        return {
            self.COMPLETED: "success",
            self.FAILED: "danger",
            self.CANCELLED: "neutral",
            self.CONSENT_PENDING: "warning",
        }.get(self.status, "accent")

    # -- money -------------------------------------------------------------- #

    @property
    def margin_inr(self):
        """Platform margin on this order — staff-only information."""
        return money(self.price_inr) - money(self.provider_cost_inr)

    @property
    def is_charged(self):
        return bool(self.charge_ref)

    @property
    def can_cancel(self):
        return self.status in self.PRE_CHARGE_STATUSES

    @property
    def charge_reference(self):
        """The idempotency key this order bills under."""
        return f"bgv:{self.pk}"

    # -- results ------------------------------------------------------------ #

    CLEAR = "CLEAR"
    DISCREPANCY = "DISCREPANCY"
    UNABLE = "UNABLE"

    @property
    def result_rows(self):
        """``[{code, label, status, notes, kind}]`` in package order."""
        results = self.result or {}
        rows = []
        for code in self.checks or []:
            entry = results.get(code) or {}
            status = entry.get("status", "")
            rows.append(
                {
                    "code": code,
                    "label": check_label(code),
                    "status": status,
                    "notes": entry.get("notes", ""),
                    "kind": {
                        self.CLEAR: "success",
                        self.DISCREPANCY: "danger",
                        self.UNABLE: "warning",
                    }.get(status, "neutral"),
                }
            )
        return rows

    @property
    def has_discrepancy(self):
        return any(row["status"] == self.DISCREPANCY for row in self.result_rows)
