"""Notification preferences, candidate opt-outs and the outbound message log."""

from django.db import models
from django.utils import timezone

from notifications import registry


class NotificationPreferenceQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)


class NotificationPreference(models.Model):
    """Per-company channel selection for one event.

    ``channels`` is a JSON list of channel keys (see ``notifications.registry``).
    A missing row means "use the computed default" — see ``notifications.api``.
    """

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="notification_preferences"
    )
    event = models.CharField(max_length=64)
    channels = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = NotificationPreferenceQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "event"], name="uniq_notification_pref_company_event"
            )
        ]
        ordering = ["event"]

    def __str__(self):
        return f"{self.company_id}:{self.event}={','.join(self.channels)}"

    @property
    def label(self):
        try:
            return registry.get_event(self.event).label
        except registry.UnknownEvent:
            return self.event.replace("_", " ").title()


class CandidateChannelOptOut(models.Model):
    """A candidate has opted out of one channel entirely (e.g. WhatsApp)."""

    profile = models.ForeignKey(
        "jobs.CandidateProfile", on_delete=models.CASCADE, related_name="channel_opt_outs"
    )
    channel = models.CharField(
        max_length=20,
        choices=[(c, registry.CHANNEL_LABELS[c]) for c in registry.OPT_OUT_CHANNELS],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "channel"], name="uniq_candidate_opt_out_profile_channel"
            )
        ]
        ordering = ["channel"]

    def __str__(self):
        return f"{self.profile_id} opted out of {self.channel}"


class OutboundMessageQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)

    def retryable(self, max_attempts=3):
        return self.filter(status=OutboundMessage.FAILED, attempts__lt=max_attempts)


class OutboundMessage(models.Model):
    """One attempted delivery on one channel — the notifications audit log."""

    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    # Delivery states reported back by the WhatsApp webhook.
    DELIVERED = "DELIVERED"
    READ = "READ"
    STATUS_CHOICES = [
        (QUEUED, "Queued"),
        (SENT, "Sent"),
        (DELIVERED, "Delivered"),
        (READ, "Read"),
        (FAILED, "Failed"),
        (SKIPPED, "Skipped"),
    ]

    company = models.ForeignKey(
        "core.Company",
        on_delete=models.CASCADE,
        related_name="outbound_messages",
        null=True,
        blank=True,
    )
    recipient_email = models.EmailField(blank=True)
    recipient_phone = models.CharField(max_length=32, blank=True)
    channel = models.CharField(
        max_length=16, choices=[(c, registry.CHANNEL_LABELS[c]) for c in registry.CHANNELS]
    )
    event = models.CharField(max_length=64)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=QUEUED)
    error = models.TextField(blank=True)
    provider_ref = models.CharField(max_length=255, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OutboundMessageQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["provider_ref"]),
        ]

    def __str__(self):
        return f"{self.event} via {self.channel} -> {self.recipient or '?'} ({self.status})"

    @property
    def recipient(self):
        return self.recipient_email or self.recipient_phone

    @property
    def is_retryable(self):
        return self.status == self.FAILED and self.attempts < 3

    @property
    def event_label(self):
        try:
            return registry.get_event(self.event).label
        except registry.UnknownEvent:
            return self.event.replace("_", " ").title()

    def mark_sent(self, provider_ref=""):
        self.status = self.SENT
        self.error = ""
        self.provider_ref = provider_ref or self.provider_ref
        self.sent_at = timezone.now()
        self.last_attempt_at = self.sent_at
        self.save(
            update_fields=[
                "status", "error", "provider_ref", "sent_at", "last_attempt_at", "attempts",
            ]
        )
        return self

    def mark_failed(self, error):
        self.status = self.FAILED
        self.error = str(error)[:2000]
        self.last_attempt_at = timezone.now()
        self.save(update_fields=["status", "error", "last_attempt_at", "attempts"])
        return self

    def mark_skipped(self, reason):
        self.status = self.SKIPPED
        self.error = str(reason)[:2000]
        self.save(update_fields=["status", "error"])
        return self
