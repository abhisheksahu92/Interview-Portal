"""The seeker side of the opportunity network: who is looking, what they saved,
and every mail they sent about it.

Three rules shape these models:

* **Mailbox credentials never sit in plaintext.** ``SeekerProfile.mailbox_config``
  is a Fernet token from :mod:`integrations.crypto`, the same treatment
  connector API keys get, so a database dump does not hand over app passwords
  or Gmail refresh tokens.
* **The send quota is counted, not derived.** ``sends_this_month`` plus
  ``month_key`` is a two-field counter that rolls over on the first send of a
  new calendar month; counting ``Outreach`` rows instead would let a deletion
  buy free sends.
* **A saved item points at exactly one thing** — an external lead or an
  internal job — enforced by a database CheckConstraint rather than by hope,
  because the two sides take completely different actions later.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from integrations.crypto import decrypt_json, encrypt_json

#: Free accounts may send this many outreach mails per calendar month.
FREE_MONTHLY_SENDS = 10

#: Guardrail on any one bulk action, however large the selection.
MAX_BULK_SENDS = 25


def month_key(when=None):
    """The "YYYY-MM" bucket a send counts against."""
    return (when or timezone.now()).strftime("%Y-%m")


class SeekerProfile(models.Model):
    """A candidate's job-hunting preferences and their own outbound mailbox."""

    NONE = "NONE"
    GMAIL = "GMAIL"
    SMTP = "SMTP"
    MAILBOX_KINDS = [(NONE, "Not connected"), (GMAIL, "Gmail"), (SMTP, "SMTP")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seeker_profile"
    )
    target_roles = models.JSONField(default=list, blank=True)
    #: Mirrors the names on ``CandidateProfile.skills``, lower-cased for matching.
    skills = models.JSONField(default=list, blank=True)
    min_budget_inr = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    remote_only = models.BooleanField(default=False)
    is_pro = models.BooleanField(default=False)
    sends_this_month = models.PositiveIntegerField(default=0)
    month_key = models.CharField(max_length=7, blank=True)
    mailbox_kind = models.CharField(max_length=8, choices=MAILBOX_KINDS, default=NONE)
    #: Fernet token over the SMTP settings or the Gmail refresh token.
    mailbox_config = models.TextField(blank=True)
    mailbox_email = models.EmailField(blank=True)
    upgrade_requested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"seeker: {self.user.email}"

    # -- mailbox credentials ------------------------------------------------
    def get_mailbox_config(self):
        """The decrypted mailbox settings, or ``{}`` when unreadable."""
        return decrypt_json(self.mailbox_config)

    def set_mailbox_config(self, value):
        self.mailbox_config = encrypt_json(value or {})

    @property
    def mailbox_ready(self):
        return self.mailbox_kind != self.NONE and bool(self.mailbox_email)

    # -- quota --------------------------------------------------------------
    @property
    def monthly_allowance(self):
        return None if self.is_pro else FREE_MONTHLY_SENDS

    def sends_used(self, when=None):
        """Sends already made in the current month; 0 once the month rolls."""
        return self.sends_this_month if self.month_key == month_key(when) else 0

    def sends_left(self, when=None):
        """``None`` means unlimited (pro)."""
        if self.is_pro:
            return None
        return max(0, FREE_MONTHLY_SENDS - self.sends_used(when))


class SavedItem(models.Model):
    """One opportunity a seeker is tracking — an external lead or one of our jobs."""

    SAVED = "SAVED"
    APPLIED = "APPLIED"
    CONTACTED = "CONTACTED"
    REPLIED = "REPLIED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"
    STATUSES = [
        (SAVED, "Saved"),
        (APPLIED, "Applied"),
        (CONTACTED, "Contacted"),
        (REPLIED, "Replied"),
        (REJECTED, "Rejected"),
        (ARCHIVED, "Archived"),
    ]

    seeker = models.ForeignKey(SeekerProfile, on_delete=models.CASCADE, related_name="saved_items")
    lead = models.ForeignKey(
        "sources.Lead",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="saved_by",
    )
    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="saved_by_seekers",
    )
    status = models.CharField(max_length=12, choices=STATUSES, default=SAVED)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # A saved row is either a lead or a job — never both, never neither.
            models.CheckConstraint(
                condition=models.Q(lead__isnull=False, job__isnull=True)
                | models.Q(lead__isnull=True, job__isnull=False),
                name="seeker_saveditem_exactly_one_target",
            ),
            models.UniqueConstraint(fields=["seeker", "lead"], name="seeker_saveditem_unique_lead"),
            models.UniqueConstraint(fields=["seeker", "job"], name="seeker_saveditem_unique_job"),
        ]

    def __str__(self):
        return self.title

    @property
    def title(self):
        target = self.lead or self.job
        return getattr(target, "title", "") or "Untitled"

    @property
    def company_name(self):
        if self.lead_id:
            return self.lead.company_name
        if self.job_id:
            return self.job.company.name
        return ""

    @property
    def url(self):
        return self.lead.url if self.lead_id else ""

    @property
    def contact_email(self):
        return self.lead.contact_email if self.lead_id else ""


class Outreach(models.Model):
    """One mail to one person about one saved item. No BCC lists, ever."""

    DRAFT = "DRAFT"
    SENT = "SENT"
    FAILED = "FAILED"
    STATUSES = [(DRAFT, "Draft"), (SENT, "Sent"), (FAILED, "Failed")]

    seeker = models.ForeignKey(SeekerProfile, on_delete=models.CASCADE, related_name="outreach")
    saved_item = models.ForeignKey(SavedItem, on_delete=models.CASCADE, related_name="outreach")
    to_email = models.EmailField()
    subject = models.CharField(max_length=300)
    body = models.TextField()
    resume_attached = models.BooleanField(default=False)
    status = models.CharField(max_length=8, choices=STATUSES, default=DRAFT)
    provider_message_id = models.CharField(max_length=200, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.to_email}: {self.subject}"
