"""Integration models: outbound webhooks, their delivery log, and connectors."""

import secrets

from django.db import models
from django.utils import timezone

from integrations.crypto import decrypt_json, encrypt_json
from integrations.events import EVENT_CHOICES, EVENTS


class EncryptedJSONField(models.TextField):
    """A JSON value persisted as a Fernet token.

    Behaves like ``JSONField`` in Python (dicts in, dicts out) but the column
    holds ciphertext, so connector API keys are encrypted at rest. An
    undecryptable token (e.g. after a ``SECRET_KEY`` rotation with no explicit
    ``INTEGRATIONS_ENCRYPTION_KEY``) reads back as ``{}``.
    """

    empty_strings_allowed = False

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("default", dict)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if kwargs.get("default") is dict:
            kwargs.pop("default")
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        if value is None:
            return {}
        return decrypt_json(value)

    def to_python(self, value):
        if value is None:
            return {}
        if isinstance(value, dict | list):
            return value
        return decrypt_json(value)

    def get_prep_value(self, value):
        if isinstance(value, str) and value.startswith("gAAAAA"):
            return value  # already a token (e.g. a queryset .update())
        return encrypt_json(value)


class OutboundWebhookQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)

    def active(self):
        return self.filter(active=True)


class OutboundWebhook(models.Model):
    """A customer HTTPS endpoint subscribed to a set of hiring events."""

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="webhooks"
    )
    name = models.CharField(max_length=120)
    url = models.URLField(max_length=500)
    secret = models.CharField(
        max_length=64,
        blank=True,
        help_text="Shared secret used to sign deliveries; generated when blank.",
    )
    events = models.JSONField(
        default=list,
        blank=True,
        help_text="Event names to send. An empty list means every event.",
    )
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_webhooks",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OutboundWebhookQuerySet.as_manager()

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "outbound webhook"

    def __str__(self):
        return f"{self.name} -> {self.url}"

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = self.new_secret()
        self.events = [name for name in (self.events or []) if name in EVENTS]
        super().save(*args, **kwargs)

    @staticmethod
    def new_secret():
        return secrets.token_hex(24)

    def rotate_secret(self):
        self.secret = self.new_secret()
        self.save(update_fields=["secret"])
        return self.secret

    def subscribes_to(self, event) -> bool:
        """True when this webhook wants ``event`` (empty list = all events)."""
        return not self.events or event in self.events

    @property
    def event_labels(self):
        labels = dict(EVENT_CHOICES)
        if not self.events:
            return ["All events"]
        return [labels.get(name, name) for name in self.events]

    @property
    def masked_secret(self):
        if not self.secret:
            return ""
        return f"{'•' * 8}{self.secret[-4:]}"


class WebhookDeliveryQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(webhook__company=company)

    def due(self, now=None):
        now = now or timezone.now()
        return self.filter(
            status=WebhookDelivery.PENDING, next_attempt_at__lte=now
        ).order_by("next_attempt_at", "pk")


class WebhookDelivery(models.Model):
    """One attempt log for one (webhook, event) pair.

    ``next_attempt_at`` drives the retry queue: a PENDING row whose time has
    come is picked up by ``manage.py deliver_webhooks``.
    """

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (SENT, "Sent"),
        (FAILED, "Failed"),
    ]

    #: Delay before attempt N+1, in seconds: 1m, 5m, 30m, 2h, 12h.
    BACKOFF_SECONDS = (60, 300, 1800, 7200, 43200)
    MAX_ATTEMPTS = 5

    webhook = models.ForeignKey(
        OutboundWebhook, on_delete=models.CASCADE, related_name="deliveries"
    )
    event = models.CharField(max_length=60, choices=EVENT_CHOICES)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    objects = WebhookDeliveryQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]
        verbose_name = "webhook delivery"
        verbose_name_plural = "webhook deliveries"

    def __str__(self):
        return f"{self.event} #{self.pk} ({self.status})"

    @property
    def company(self):
        return self.webhook.company

    @property
    def attempts_remaining(self):
        return max(self.MAX_ATTEMPTS - self.attempts, 0)

    def backoff_for(self, attempt):
        """Seconds to wait before attempt number ``attempt + 1``."""
        index = min(max(attempt, 1), len(self.BACKOFF_SECONDS)) - 1
        return self.BACKOFF_SECONDS[index]

    def reset_for_redelivery(self):
        """Requeue a FAILED/SENT delivery for an immediate fresh attempt."""
        self.status = self.PENDING
        self.attempts = 0
        self.last_error = ""
        self.response_code = None
        self.next_attempt_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "attempts",
                "last_error",
                "response_code",
                "next_attempt_at",
            ]
        )
        return self


class ConnectorConfigQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)

    def active(self):
        return self.filter(active=True)

    def hrms(self):
        return self.filter(kind__in=ConnectorConfig.HRMS_KINDS)


class ConnectorConfig(models.Model):
    """Per-company credentials for one third-party connector.

    ``settings`` is a dict of adapter-specific values (``api_key``,
    ``subdomain``, ...) encrypted at rest — see :mod:`integrations.crypto`.
    """

    KEKA = "KEKA"
    ZOHO_PEOPLE = "ZOHO_PEOPLE"
    GREYTHR = "GREYTHR"
    BACKGROUND_CHECK = "BACKGROUND_CHECK"
    KIND_CHOICES = [
        (KEKA, "Keka HRMS"),
        (ZOHO_PEOPLE, "Zoho People"),
        (GREYTHR, "greytHR"),
        (BACKGROUND_CHECK, "Background check"),
    ]
    #: Connectors that receive ``push_hire`` when an application is hired.
    HRMS_KINDS = (KEKA, ZOHO_PEOPLE, GREYTHR)

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="connector_configs"
    )
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    settings = EncryptedJSONField(blank=True)
    active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ConnectorConfigQuerySet.as_manager()

    class Meta:
        ordering = ["kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "kind"], name="unique_connector_per_company"
            )
        ]
        verbose_name = "connector configuration"

    def __str__(self):
        return f"{self.get_kind_display()} ({self.company_id})"

    @property
    def is_hrms(self):
        return self.kind in self.HRMS_KINDS

    def adapter(self):
        from integrations.connectors import adapter_for

        return adapter_for(self)

    def log(self, status, detail="", **extra):
        return ConnectorRun.objects.create(
            config=self,
            kind=self.kind,
            status=status,
            detail=detail or "",
            context=extra or {},
        )


class ConnectorRun(models.Model):
    """Audit row for one connector call (a hire push, a background check)."""

    OK = "OK"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    STATUS_CHOICES = [
        (OK, "Ok"),
        (SKIPPED, "Skipped"),
        (ERROR, "Error"),
    ]

    config = models.ForeignKey(
        ConnectorConfig,
        on_delete=models.CASCADE,
        related_name="runs",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=30, choices=ConnectorConfig.KIND_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=OK)
    detail = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "connector run"

    def __str__(self):
        return f"{self.kind}: {self.status}"
