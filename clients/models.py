"""Client-portal models: staffing clients, tokenised access links, submissions."""

import secrets
from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def generate_token() -> str:
    """A URL-safe, unguessable access token for a client portal link."""
    return secrets.token_urlsafe(32)


class ClientQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)


class Client(models.Model):
    """An end client of a staffing firm, to whom candidates get submitted."""

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="clients"
    )
    name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    logo = models.FileField(upload_to="client_logos/", blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ClientQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_client_per_company")
        ]

    def __str__(self):
        return self.name

    @property
    def active_accesses(self):
        return [access for access in self.accesses.all() if access.is_active]


class ClientAccess(models.Model):
    """A magic-link grant letting one client contact open the portal."""

    DEFAULT_VALID_DAYS = 30

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="accesses")
    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=generate_token)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "client accesses"

    def __str__(self):
        return f"{self.email} → {self.client}"

    @property
    def company(self):
        return self.client.company

    @property
    def is_expired(self):
        return self.expires_at is not None and self.expires_at <= timezone.now()

    @property
    def is_active(self):
        return not self.revoked and not self.is_expired

    def touch(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])

    def revoke(self):
        self.revoked = True
        self.save(update_fields=["revoked"])

    def rotate(self, days=None):
        """Issue a fresh token/expiry on the same row (used by "resend link")."""
        self.token = generate_token()
        self.revoked = False
        self.expires_at = timezone.now() + timedelta(days=days or self.DEFAULT_VALID_DAYS)
        self.save(update_fields=["token", "revoked", "expires_at"])
        return self


class Submission(models.Model):
    """One candidate application put in front of one client."""

    SUBMITTED = "SUBMITTED"
    SHORTLISTED = "SHORTLISTED"
    REJECTED = "REJECTED"
    INTERVIEW_REQUESTED = "INTERVIEW_REQUESTED"
    HIRED = "HIRED"
    STATUS_CHOICES = [
        (SUBMITTED, "Submitted"),
        (SHORTLISTED, "Shortlisted"),
        (REJECTED, "Rejected"),
        (INTERVIEW_REQUESTED, "Interview requested"),
        (HIRED, "Hired"),
    ]
    # Statuses a client may set from the portal feedback form.
    CLIENT_DECISIONS = [SHORTLISTED, REJECTED, INTERVIEW_REQUESTED]

    application = models.ForeignKey(
        "jobs.Application", on_delete=models.CASCADE, related_name="client_submissions"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="submissions")
    submitted_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_submissions",
    )
    note = models.TextField(blank=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default=SUBMITTED)
    client_feedback = models.TextField(blank=True)
    client_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "client"], name="uniq_submission_per_app_client"
            )
        ]

    def __str__(self):
        return f"{self.application} → {self.client}"

    @property
    def company(self):
        return self.client.company

    @property
    def job(self):
        return self.application.job

    @property
    def candidate(self):
        return self.application.candidate

    @property
    def is_decided(self):
        return self.status != self.SUBMITTED

    def record_client_decision(self, status, feedback="", rating=None):
        """Apply a portal decision and stamp ``decided_at``."""
        self.status = status
        self.client_feedback = feedback or ""
        self.client_rating = rating
        self.decided_at = timezone.now()
        self.save(
            update_fields=["status", "client_feedback", "client_rating", "decided_at"]
        )
        return self

    def timeline(self):
        """Ordered events for the recruiter-facing status timeline."""
        events = [
            {
                "label": "Submitted",
                "at": self.created_at,
                "detail": self.note,
                "icon": "bi-send",
            }
        ]
        if self.is_decided:
            events.append(
                {
                    "label": self.get_status_display(),
                    "at": self.decided_at,
                    "detail": self.client_feedback,
                    "icon": "bi-chat-left-text",
                    "rating": self.client_rating,
                }
            )
        return events
