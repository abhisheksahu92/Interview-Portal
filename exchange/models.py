"""Exchange models: the agency requirement network.

Four rows carry the whole feature:

* :class:`PartnerLink`       — mutual trust between two companies.
* :class:`ExchangeRequirement` — a job published to the network (client anonymised).
* :class:`ExchangeSubmission`  — a partner's candidate, contact masked until reveal.
* :class:`ExchangeDeal`        — the money once a submission is hired.

Anti-leak rules live on the models (not the templates): every read of a
candidate's contact details goes through :meth:`ExchangeSubmission.snapshot_for`
and every read of a requester's end client through
:meth:`ExchangeRequirement.client_label_for`.
"""

import hashlib
from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils import timezone

from core.permissions import for_company

#: Placeholder shown wherever a masked contact field would go.
REDACTED = "REDACTED"
#: Placeholder shown instead of an end client that the viewer may not see.
ANON_CLIENT = "Confidential client"

CONTACT_FIELDS = ("name", "email", "phone")


def email_hash(value) -> str:
    """Stable hash of an email, used to dedupe submissions to one requirement."""
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def money(value) -> Decimal:
    """A Decimal rounded to paise, for every share this app computes."""
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CompanyScopedQuerySet(models.QuerySet):
    def for_company(self, company):
        return for_company(self, company)


class PartnerLink(models.Model):
    """A trust edge between two companies; one row per unordered pair."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (ACTIVE, "Active"),
        (BLOCKED, "Blocked"),
    ]

    from_company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="partner_links_sent"
    )
    to_company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="partner_links_received"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    created_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partner_links_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_company", "to_company"], name="exchange_partner_unique_pair"
            ),
            models.CheckConstraint(
                condition=~models.Q(from_company=models.F("to_company")),
                name="exchange_partner_not_self",
            ),
        ]
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return f"{self.from_company} ↔ {self.to_company} ({self.status})"

    # --- lookups ---------------------------------------------------------

    @classmethod
    def between(cls, company_a, company_b):
        """The link joining two companies in either direction, or None."""
        if company_a is None or company_b is None:
            return None
        return (
            cls.objects.filter(
                models.Q(from_company=company_a, to_company=company_b)
                | models.Q(from_company=company_b, to_company=company_a)
            )
            .select_related("from_company", "to_company")
            .first()
        )

    @classmethod
    def involving(cls, company):
        """Every link ``company`` is on either side of."""
        if company is None:
            return cls.objects.none()
        return cls.objects.filter(
            models.Q(from_company=company) | models.Q(to_company=company)
        ).select_related("from_company", "to_company", "created_by")

    @classmethod
    def active_partner_ids(cls, company):
        """Ids of companies with an ACTIVE link to ``company``."""
        ids = set()
        for link in cls.involving(company).filter(status=cls.ACTIVE):
            ids.add(link.to_company_id if link.from_company_id == company.pk else link.from_company_id)
        return ids

    @classmethod
    def are_partners(cls, company_a, company_b):
        link = cls.between(company_a, company_b)
        return link is not None and link.status == cls.ACTIVE

    # --- helpers ---------------------------------------------------------

    def other_company(self, company):
        """The company on the far side of this link from ``company``."""
        return self.to_company if self.from_company_id == company.pk else self.from_company

    def involves(self, company):
        return company is not None and company.pk in (self.from_company_id, self.to_company_id)

    def is_incoming_for(self, company):
        """True when ``company`` is the one that has to accept."""
        return self.status == self.PENDING and self.to_company_id == getattr(company, "pk", None)


class ExchangeRequirement(models.Model):
    """A role one company publishes to the exchange."""

    PARTNERS = "PARTNERS"
    NETWORK = "NETWORK"
    VISIBILITY_CHOICES = [
        (PARTNERS, "Partners only"),
        (NETWORK, "Whole network"),
    ]

    OPEN = "OPEN"
    FILLED = "FILLED"
    CLOSED = "CLOSED"
    STATUS_CHOICES = [
        (OPEN, "Open"),
        (FILLED, "Filled"),
        (CLOSED, "Closed"),
    ]

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="exchange_requirements"
    )
    job = models.ForeignKey(
        "jobs.Job", on_delete=models.CASCADE, related_name="exchange_requirements"
    )
    title = models.CharField(max_length=200)
    #: The real end client. Never rendered directly — see ``client_label_for``.
    client_name = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    skills = models.ManyToManyField(
        "jobs.Skill", blank=True, related_name="exchange_requirements"
    )
    location = models.CharField(max_length=150, blank=True)
    budget_ctc_min = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    budget_ctc_max = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    fee_split_pct = models.PositiveSmallIntegerField(default=50)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default=PARTNERS)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=OPEN)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exchange_requirements_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "visibility"]),
            models.Index(fields=["company", "status"]),
        ]

    def __str__(self):
        return self.title

    @property
    def is_expired(self):
        return self.expires_at is not None and self.expires_at <= timezone.now()

    @property
    def is_open(self):
        return self.status == self.OPEN and not self.is_expired

    @property
    def budget_label(self):
        from web.templatetags.web_money import inr

        low, high = self.budget_ctc_min, self.budget_ctc_max
        if low is None and high is None:
            return "Not disclosed"
        # Indian grouping (18,00,000), the same as every other salary figure
        # on this platform — never 1,800,000.
        if low is not None and high is not None:
            return f"₹{inr(round(low))} – ₹{inr(round(high))}"
        return f"₹{inr(round(low or high))}"

    # --- anti-leak -------------------------------------------------------

    def client_label_for(self, viewer_company):
        """The end client as ``viewer_company`` is allowed to see it.

        The owning company always sees it. A partner sees it only when the
        requirement is PARTNERS-visible; on a NETWORK requirement the client is
        anonymised for everyone but the owner.
        """
        if viewer_company is not None and viewer_company.pk == self.company_id:
            return self.client_name or ""
        if not self.client_name:
            return ""
        if self.visibility == self.PARTNERS and PartnerLink.are_partners(
            self.company, viewer_company
        ):
            return self.client_name
        return ANON_CLIENT

    def is_visible_to(self, viewer_company):
        """True when ``viewer_company`` may see this requirement in a feed."""
        if viewer_company is None or viewer_company.pk == self.company_id:
            return False
        if self.visibility == self.NETWORK:
            return True
        return PartnerLink.are_partners(self.company, viewer_company)

    def submission_from(self, company):
        if company is None:
            return None
        return self.submissions.filter(responding_company=company).first()


class ExchangeSubmission(models.Model):
    """A candidate a partner offers against a requirement."""

    SUBMITTED = "SUBMITTED"
    SHORTLISTED = "SHORTLISTED"
    INTERVIEWING = "INTERVIEWING"
    HIRED = "HIRED"
    REJECTED = "REJECTED"
    STATUS_CHOICES = [
        (SUBMITTED, "Submitted"),
        (SHORTLISTED, "Shortlisted"),
        (INTERVIEWING, "Interviewing"),
        (HIRED, "Hired"),
        (REJECTED, "Rejected"),
    ]

    requirement = models.ForeignKey(
        ExchangeRequirement, on_delete=models.CASCADE, related_name="submissions"
    )
    responding_company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="exchange_submissions"
    )
    #: {name, email, phone, headline, experience_years, location, skills: [...]}
    candidate_snapshot = models.JSONField(default=dict, blank=True)
    email_hash = models.CharField(max_length=64, blank=True)
    resume_file = models.FileField(upload_to="exchange/resumes/", blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=SUBMITTED)
    revealed_at = models.DateTimeField(null=True, blank=True)
    talent_profile = models.ForeignKey(
        "talent.TalentProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exchange_submissions",
    )
    candidate_profile = models.ForeignKey(
        "jobs.CandidateProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exchange_submissions",
    )
    created_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exchange_submissions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["requirement", "email_hash"],
                condition=~models.Q(email_hash=""),
                name="exchange_submission_unique_email_per_requirement",
            )
        ]
        indexes = [
            models.Index(fields=["requirement", "status"]),
            models.Index(fields=["responding_company", "status"]),
        ]

    def __str__(self):
        return f"{self.reference} → {self.requirement.title}"

    def save(self, *args, **kwargs):
        if not self.email_hash:
            self.email_hash = email_hash((self.candidate_snapshot or {}).get("email"))
        super().save(*args, **kwargs)

    # --- identity --------------------------------------------------------

    @property
    def is_revealed(self):
        return self.revealed_at is not None

    @property
    def reference(self):
        """A stable, contact-free handle for a masked card."""
        return f"CAND-{self.pk or 0:05d}"

    @property
    def full_snapshot(self):
        return dict(self.candidate_snapshot or {})

    @property
    def masked_snapshot(self):
        """The snapshot with every contact field replaced by ``REDACTED``."""
        data = self.full_snapshot
        for field in CONTACT_FIELDS:
            if field in data or field == "name":
                data[field] = REDACTED
        data["masked"] = True
        return data

    def snapshot_for(self, viewer_company):
        """What ``viewer_company`` may read of this candidate.

        The submitting company always sees its own candidate. The requester sees
        contact details only after :func:`exchange.services.reveal`. Anybody else
        gets the masked snapshot, contact fields included.
        """
        viewer_pk = getattr(viewer_company, "pk", None)
        if viewer_pk == self.responding_company_id:
            return self.full_snapshot
        if viewer_pk == self.requirement.company_id and self.is_revealed:
            return self.full_snapshot
        return self.masked_snapshot

    def can_reveal(self, viewer_company):
        return (
            getattr(viewer_company, "pk", None) == self.requirement.company_id
            and not self.is_revealed
        )

    @property
    def display_skills(self):
        return list((self.candidate_snapshot or {}).get("skills") or [])


class ExchangeDeal(models.Model):
    """The money for a hired submission, split between the two agencies."""

    PENDING = "PENDING"
    INVOICED = "INVOICED"
    SETTLED = "SETTLED"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (INVOICED, "Invoiced"),
        (SETTLED, "Settled"),
    ]

    DEFAULT_PLATFORM_FEE_PCT = 12

    submission = models.OneToOneField(
        ExchangeSubmission, on_delete=models.CASCADE, related_name="deal"
    )
    placement_fee_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    split_pct = models.PositiveSmallIntegerField(default=50)
    platform_fee_pct = models.PositiveSmallIntegerField(default=DEFAULT_PLATFORM_FEE_PCT)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    disputed = models.BooleanField(default=False)
    dispute_reason = models.TextField(blank=True)
    disputed_at = models.DateTimeField(null=True, blank=True)
    charged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Deal #{self.pk} · ₹{self.placement_fee_inr:,.0f}"

    # --- parties ---------------------------------------------------------

    @property
    def requester_company(self):
        return self.submission.requirement.company

    @property
    def responder_company(self):
        return self.submission.responding_company

    # --- money -----------------------------------------------------------

    @property
    def responder_gross(self):
        """The responder's slice of the placement fee, before the platform fee."""
        return money(Decimal(self.placement_fee_inr) * Decimal(self.split_pct) / Decimal(100))

    @property
    def requester_gross(self):
        return money(Decimal(self.placement_fee_inr) - self.responder_gross)

    @property
    def responder_platform_fee(self):
        return money(self.responder_gross * Decimal(self.platform_fee_pct) / Decimal(100))

    @property
    def requester_platform_fee(self):
        return money(self.requester_gross * Decimal(self.platform_fee_pct) / Decimal(100))

    @property
    def platform_fee(self):
        """Total platform fee — the two sides' shares, so it never drifts."""
        return money(self.responder_platform_fee + self.requester_platform_fee)

    @property
    def responder_share(self):
        return money(self.responder_gross - self.responder_platform_fee)

    @property
    def requester_share(self):
        return money(self.requester_gross - self.requester_platform_fee)

    def share_for(self, company):
        """The net share payable to ``company``, or None when uninvolved."""
        pk = getattr(company, "pk", None)
        if pk == self.responder_company.pk:
            return self.responder_share
        if pk == self.requester_company.pk:
            return self.requester_share
        return None

    def platform_fee_for(self, company):
        pk = getattr(company, "pk", None)
        if pk == self.responder_company.pk:
            return self.responder_platform_fee
        if pk == self.requester_company.pk:
            return self.requester_platform_fee
        return None
