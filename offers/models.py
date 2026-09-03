"""Offer letter models: templates, offers, and their audit trail."""

import secrets

from django.db import models
from django.urls import reverse
from django.utils import timezone

from offers.rendering import PLACEHOLDERS, render_body

DEFAULT_TEMPLATE_NAME = "Standard offer letter"
DEFAULT_TEMPLATE_SUBJECT = "Your offer from {{company_name}}"
DEFAULT_TEMPLATE_BODY = """<p>Dear {{candidate_name}},</p>
<p>We are delighted to offer you the position of <strong>{{job_title}}</strong>
at {{company_name}}{{location}}.</p>
<ul>
  <li>Annual compensation: {{currency}} {{salary}}</li>
  <li>Proposed joining date: {{joining_date}}</li>
</ul>
<p>Please review and sign this offer by {{expires_at}}.</p>
<p>Warm regards,<br>{{company_name}} Talent Team</p>
"""


class OfferTemplateQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)


class OfferTemplate(models.Model):
    """A reusable offer letter body with ``{{placeholder}}`` slots."""

    PLACEHOLDERS = PLACEHOLDERS

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="offer_templates"
    )
    name = models.CharField(max_length=120)
    subject = models.CharField(max_length=200, default=DEFAULT_TEMPLATE_SUBJECT)
    body_html = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OfferTemplateQuerySet.as_manager()

    class Meta:
        ordering = ["-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_offer_template_name_per_company"
            )
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            type(self).objects.filter(company=self.company).exclude(pk=self.pk).update(
                is_default=False
            )

    def render(self, context):
        """Safely substitute ``context`` into :attr:`body_html`."""
        return render_body(self.body_html, context)

    def render_subject(self, context):
        return render_body(self.subject, context, escape_values=False)

    @classmethod
    def default_for(cls, company):
        """The company's default template, seeded lazily on first use."""
        existing = cls.objects.filter(company=company, is_default=True).first()
        if existing is not None:
            return existing
        template, _ = cls.objects.get_or_create(
            company=company,
            name=DEFAULT_TEMPLATE_NAME,
            defaults={
                "subject": DEFAULT_TEMPLATE_SUBJECT,
                "body_html": DEFAULT_TEMPLATE_BODY,
                "is_default": True,
            },
        )
        if not template.is_default:
            template.is_default = True
            template.save(update_fields=["is_default"])
        return template


class OfferQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(application__job__company=company)

    def open_offers(self):
        return self.filter(status__in=Offer.OPEN_STATUSES)

    def expiring_before(self, when):
        return self.open_offers().filter(expires_at__lt=when)


class Offer(models.Model):
    """An offer letter issued against an application, signed by click-to-sign."""

    DRAFT = "DRAFT"
    SENT = "SENT"
    VIEWED = "VIEWED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SENT, "Sent"),
        (VIEWED, "Viewed"),
        (ACCEPTED, "Accepted"),
        (DECLINED, "Declined"),
        (EXPIRED, "Expired"),
        (WITHDRAWN, "Withdrawn"),
    ]
    #: Statuses where the candidate may still act on the offer.
    OPEN_STATUSES = (SENT, VIEWED)
    #: Statuses that end the offer's life.
    CLOSED_STATUSES = (ACCEPTED, DECLINED, EXPIRED, WITHDRAWN)

    application = models.ForeignKey(
        "jobs.Application", on_delete=models.CASCADE, related_name="offers"
    )
    template = models.ForeignKey(
        OfferTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="offers",
    )
    salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default="INR")
    joining_date = models.DateField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)
    body_rendered = models.TextField(blank=True)
    pdf = models.FileField(upload_to="offers/", blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=DRAFT)
    sign_token = models.CharField(max_length=64, unique=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    signed_name = models.CharField(max_length=150, blank=True)
    signed_ip = models.GenericIPAddressField(null=True, blank=True)
    signed_user_agent = models.CharField(max_length=400, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "core.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="offers_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OfferQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Offer #{self.pk} — {self.application}"

    def save(self, *args, **kwargs):
        if not self.sign_token:
            self.sign_token = self.new_token()
        super().save(*args, **kwargs)

    @staticmethod
    def new_token():
        return secrets.token_urlsafe(32)[:48]

    # --- derived data ----------------------------------------------------

    @property
    def company(self):
        return self.application.job.company

    @property
    def candidate_user(self):
        return self.application.candidate.user

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_signable(self):
        return self.is_open and not self.is_expired

    @property
    def expiring_soon(self):
        """Open and expiring within three days."""
        if not (self.is_open and self.expires_at):
            return False
        delta = self.expires_at - timezone.now()
        return timezone.timedelta(0) < delta <= timezone.timedelta(days=3)

    def sign_path(self):
        return reverse("offers:sign", args=[self.sign_token])

    def sign_url(self, request=None):
        path = self.sign_path()
        if request is not None:
            return request.build_absolute_uri(path)
        return path

    def log(self, kind, **meta):
        return OfferEvent.objects.create(offer=self, kind=kind, meta=meta or {})


class OfferEvent(models.Model):
    """One entry in an offer's audit trail."""

    CREATED = "CREATED"
    SENT = "SENT"
    RESENT = "RESENT"
    VIEWED = "VIEWED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"
    PDF_GENERATED = "PDF_GENERATED"
    KIND_CHOICES = [
        (CREATED, "Created"),
        (SENT, "Sent"),
        (RESENT, "Resent"),
        (VIEWED, "Viewed"),
        (ACCEPTED, "Accepted"),
        (DECLINED, "Declined"),
        (WITHDRAWN, "Withdrawn"),
        (EXPIRED, "Expired"),
        (PDF_GENERATED, "PDF generated"),
    ]

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["at", "pk"]

    def __str__(self):
        return f"{self.offer_id} · {self.kind}"
