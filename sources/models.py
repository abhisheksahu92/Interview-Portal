"""Opportunity sources and the leads harvested from them.

Two rows, one job each:

* :class:`Source` is operator-facing bookkeeping — which feeds are on, what
  each adapter needs (an ATS board slug lives in ``config``), and how the last
  run went. Everything is global: leads are cross-tenant inventory, not a
  tenant's own data.
* :class:`Lead` is a *pointer* to somebody else's posting. We deliberately keep
  a short snippet and the source link rather than the full text — the posting
  belongs to whoever wrote it, and a link keeps the seeker on the original.

``content_hash`` is what makes repeated runs cheap and idempotent: the same
posting re-appearing on a second feed collapses onto one row.
"""

import hashlib

from django.db import models
from django.utils import timezone

#: A lead nobody has re-confirmed for this long is presumed filled.
STALE_AFTER_DAYS = 45

#: Snippets are capped rather than stored whole - see the module docstring.
SNIPPET_CHARS = 600


def content_hash(title, company_name, snippet):
    """Stable identity for a posting: title + company + the first 300 chars.

    Feeds reformat descriptions constantly (tracking params, boilerplate
    footers), so hashing the whole body would defeat the point of hashing.
    """
    parts = [
        " ".join((title or "").lower().split()),
        " ".join((company_name or "").lower().split()),
        " ".join((snippet or "").lower().split())[:300],
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class Source(models.Model):
    """One upstream feed. Disabled rows are skipped by every runner."""

    API = "API"
    RSS = "RSS"
    ATS = "ATS"
    KINDS = [(API, "API"), (RSS, "RSS"), (ATS, "ATS board")]

    OK = "OK"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=8, choices=KINDS, default=API)
    enabled = models.BooleanField(default=True)
    #: Adapter parameters, e.g. ``{"slug": "stripe"}`` for an ATS board.
    config = models.JSONField(default=dict, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=16, blank=True)
    last_error = models.TextField(blank=True)
    items_seen = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "slug"]

    def __str__(self):
        return self.name or self.slug

    @property
    def adapter_slug(self):
        """ATS rows share one adapter per vendor; the board slug is in config."""
        return self.config.get("adapter") or self.slug.split(":")[0]


class LeadQuerySet(models.QuerySet):
    def live(self):
        return self.filter(is_active=True)


class Lead(models.Model):
    """A single opportunity pointing back at its original posting."""

    JOB = "JOB"
    FREELANCE = "FREELANCE"
    GIG = "GIG"
    KINDS = [(JOB, "Job"), (FREELANCE, "Freelance"), (GIG, "Gig")]

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="leads")
    external_id = models.CharField(max_length=128, blank=True)
    kind = models.CharField(max_length=12, choices=KINDS, default=JOB)
    title = models.CharField(max_length=300)
    company_name = models.CharField(max_length=200, blank=True)
    snippet = models.TextField(blank=True)
    url = models.URLField(max_length=600)
    contact_email = models.EmailField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    remote = models.BooleanField(default=False)
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, blank=True)
    budget_text = models.CharField(max_length=120, blank=True)
    tags = models.JSONField(default=list, blank=True)
    #: Normalised lower-case skill names; the seeker feed matches on these.
    skills = models.JSONField(default=list, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    content_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    objects = LeadQuerySet.as_manager()

    class Meta:
        ordering = ["-posted_at", "-fetched_at"]
        indexes = [
            models.Index(fields=["kind", "-posted_at"]),
            models.Index(fields=["is_active", "-posted_at"]),
        ]

    def __str__(self):
        return f"{self.title} @ {self.company_name}" if self.company_name else self.title
