"""Models for the scheduling app.

Four concerns:

* :class:`InterviewerAvailability` — the weekly windows an interviewer offers,
  expressed in that interviewer's own timezone.
* :class:`CalendarConnection` — an OAuth link to Google/Outlook so busy time is
  respected and confirmed interviews land on the interviewer's calendar.
* :class:`Interview` — a proposed/confirmed interview for an application, with a
  candidate-facing ``booking_token``.
* :class:`InterviewSlotProposal` — the concrete slots offered to a candidate for
  a proposal (optional; kept for auditing what was shown).
"""

import secrets
from datetime import timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from django.db import models
from django.utils import timezone as dj_timezone

DEFAULT_TIMEZONE = "UTC"

WEEKDAYS = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
]


@lru_cache(maxsize=1)
def known_timezones():
    """Cached set of IANA zone names (the scan is surprisingly expensive)."""
    return frozenset(available_timezones())


def valid_timezone(name, fallback=DEFAULT_TIMEZONE):
    """Return ``name`` when it is a real IANA zone, else ``fallback``."""
    if name and name in known_timezones():
        return name
    return fallback


@lru_cache(maxsize=256)
def zone(name):
    """A :class:`zoneinfo.ZoneInfo` for ``name``, falling back to UTC."""
    return ZoneInfo(valid_timezone(name))


class CompanyScopedQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)


class InterviewerAvailability(models.Model):
    """A recurring weekly window during which an interviewer can be booked."""

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="interviewer_availability"
    )
    user = models.ForeignKey(
        "core.User", on_delete=models.CASCADE, related_name="interviewer_availability"
    )
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS)
    start = models.TimeField(help_text="Local start time in the timezone below.")
    end = models.TimeField(help_text="Local end time in the timezone below.")
    timezone = models.CharField(max_length=64, default=DEFAULT_TIMEZONE)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedQuerySet.as_manager()

    class Meta:
        ordering = ["weekday", "start"]
        verbose_name_plural = "interviewer availability"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "user", "weekday", "start", "end"],
                name="uniq_availability_window",
            )
        ]

    def __str__(self):
        return f"{self.user} {self.get_weekday_display()} {self.start}-{self.end} ({self.timezone})"

    def save(self, *args, **kwargs):
        self.timezone = valid_timezone(self.timezone)
        super().save(*args, **kwargs)

    @property
    def tzinfo(self):
        return zone(self.timezone)


class CalendarConnection(models.Model):
    """An OAuth connection to an external calendar for one user."""

    GOOGLE = "GOOGLE"
    OUTLOOK = "OUTLOOK"
    PROVIDER_CHOICES = [
        (GOOGLE, "Google Calendar"),
        (OUTLOOK, "Outlook Calendar"),
    ]

    user = models.ForeignKey(
        "core.User", on_delete=models.CASCADE, related_name="calendar_connections"
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    tokens = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    account_email = models.EmailField(blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["provider"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "provider"], name="uniq_calendar_connection_per_provider"
            )
        ]

    def __str__(self):
        return f"{self.user} — {self.get_provider_display()}"

    @property
    def is_live(self):
        """True when this connection can actually be used for API calls."""
        return bool(self.enabled and self.tokens)


class Interview(models.Model):
    """A single interview slot for an application."""

    TOKEN_BYTES = 24
    BOOKING_WINDOW_DAYS = 14

    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    RESCHEDULED = "RESCHEDULED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    STATUS_CHOICES = [
        (PROPOSED, "Proposed"),
        (CONFIRMED, "Confirmed"),
        (RESCHEDULED, "Rescheduled"),
        (CANCELLED, "Cancelled"),
        (COMPLETED, "Completed"),
    ]
    #: statuses that still occupy the interviewers' calendars
    BLOCKING_STATUSES = (PROPOSED, CONFIRMED, RESCHEDULED)
    #: statuses a candidate may still act on from the booking page
    OPEN_STATUSES = (PROPOSED, CONFIRMED, RESCHEDULED)

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="interviews"
    )
    application = models.ForeignKey(
        "jobs.Application", on_delete=models.CASCADE, related_name="interviews"
    )
    stage = models.ForeignKey(
        "jobs.PipelineStage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interviews",
    )
    interviewers = models.ManyToManyField(
        "core.User", related_name="interviews", blank=True
    )
    scheduled_start = models.DateTimeField(null=True, blank=True, help_text="Stored in UTC.")
    scheduled_end = models.DateTimeField(null=True, blank=True, help_text="Stored in UTC.")
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    timezone = models.CharField(
        max_length=64, default=DEFAULT_TIMEZONE, help_text="Timezone the slot is presented in."
    )
    location_or_link = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PROPOSED)
    booking_token = models.CharField(max_length=64, unique=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interviews_created",
    )
    notes = models.TextField(blank=True)
    reminder_24h_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_1h_sent_at = models.DateTimeField(null=True, blank=True)
    external_event_ids = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedQuerySet.as_manager()

    class Meta:
        ordering = ["scheduled_start", "-created_at"]

    def __str__(self):
        when = self.scheduled_start.isoformat() if self.scheduled_start else "unscheduled"
        return f"Interview({self.application_id}) {when} [{self.status}]"

    def save(self, *args, **kwargs):
        if not self.booking_token:
            self.booking_token = self.new_token()
        if not self.token_expires_at:
            self.token_expires_at = self.default_token_expiry()
        self.timezone = valid_timezone(self.timezone)
        if self.company_id is None and self.application_id:
            self.company = self.application.job.company
        super().save(*args, **kwargs)

    @staticmethod
    def new_token():
        return secrets.token_urlsafe(Interview.TOKEN_BYTES)

    @classmethod
    def default_token_expiry(cls):
        return dj_timezone.now() + timedelta(days=cls.BOOKING_WINDOW_DAYS * 2)

    @property
    def tzinfo(self):
        return zone(self.timezone)

    @property
    def is_token_expired(self):
        return bool(self.token_expires_at and dj_timezone.now() >= self.token_expires_at)

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_past(self):
        return bool(self.scheduled_end and self.scheduled_end < dj_timezone.now())

    @property
    def candidate_user(self):
        return getattr(self.application.candidate, "user", None)

    def local_start(self, tz=None):
        if self.scheduled_start is None:
            return None
        return self.scheduled_start.astimezone(zone(tz) if tz else self.tzinfo)

    def local_end(self, tz=None):
        if self.scheduled_end is None:
            return None
        return self.scheduled_end.astimezone(zone(tz) if tz else self.tzinfo)

    def summary(self):
        job = self.application.job
        stage = self.stage.name if self.stage else "Interview"
        return f"{stage}: {job.title}"

    def booking_path(self):
        from django.urls import reverse

        return reverse("scheduling:book", args=[self.booking_token])


class InterviewSlotProposal(models.Model):
    """One slot offered to the candidate for an interview proposal."""

    interview = models.ForeignKey(
        Interview, on_delete=models.CASCADE, related_name="slot_proposals"
    )
    start = models.DateTimeField(help_text="Stored in UTC.")
    end = models.DateTimeField(help_text="Stored in UTC.")
    chosen = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start"]
        constraints = [
            models.UniqueConstraint(
                fields=["interview", "start"], name="uniq_slot_proposal_per_start"
            )
        ]

    def __str__(self):
        return f"{self.interview_id} @ {self.start.isoformat()}"
