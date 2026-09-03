"""Partner-programme, white-label and self-hosted-licence models."""

import secrets
from decimal import Decimal

from django.db import models
from django.utils import timezone


class Reseller(models.Model):
    """A partner who refers companies and earns commission on their invoices."""

    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=40, unique=True)
    contact_email = models.EmailField(blank=True)
    commission_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("20"))
    active = models.BooleanField(default=True)
    token = models.CharField(max_length=64, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(24)
        if self.code:
            self.code = self.code.strip().lower()
        super().save(*args, **kwargs)

    def rotate_token(self):
        self.token = secrets.token_urlsafe(24)
        self.save(update_fields=["token"])
        return self.token


class Referral(models.Model):
    """Records that ``company`` signed up through ``reseller``."""

    reseller = models.ForeignKey(Reseller, on_delete=models.CASCADE, related_name="referrals")
    company = models.OneToOneField(
        "core.Company", on_delete=models.CASCADE, related_name="referral"
    )
    signed_up_at = models.DateTimeField(default=timezone.now)
    first_payment_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-signed_up_at"]

    def __str__(self):
        return f"{self.company} <- {self.reseller.code}"


class CommissionLedger(models.Model):
    """One commission line, keyed to the invoice reference that produced it."""

    reseller = models.ForeignKey(Reseller, on_delete=models.CASCADE, related_name="commissions")
    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="partner_commissions"
    )
    invoice_ref = models.CharField(max_length=80)
    amount_inr = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    commission_inr = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    created_at = models.DateTimeField(auto_now_add=True)
    paid_out_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["reseller", "invoice_ref"], name="partners_unique_commission_invoice"
            )
        ]

    def __str__(self):
        return f"{self.reseller.code} {self.invoice_ref} = {self.commission_inr}"

    @property
    def is_paid(self):
        return self.paid_out_at is not None


class WhiteLabel(models.Model):
    """Per-company branding overrides applied to the base template and emails."""

    company = models.OneToOneField(
        "core.Company", on_delete=models.CASCADE, related_name="white_label"
    )
    brand_name = models.CharField(max_length=120, blank=True)
    logo = models.ImageField(upload_to="whitelabel/", blank=True)
    primary_color = models.CharField(max_length=20, blank=True)
    custom_domain = models.CharField(max_length=200, blank=True)
    hide_powered_by = models.BooleanField(default=False)
    email_from_name = models.CharField(max_length=120, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "white label"
        verbose_name_plural = "white labels"

    def __str__(self):
        return f"white-label for {self.company}"


class License(models.Model):
    """A signed self-hosted licence key."""

    SELF_HOSTED = "SELF_HOSTED"
    KIND_CHOICES = [(SELF_HOSTED, "Self hosted")]

    company = models.ForeignKey("core.Company", on_delete=models.CASCADE, related_name="licenses")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=SELF_HOSTED)
    key = models.CharField(max_length=255, unique=True)
    seats = models.PositiveIntegerField(default=5)
    expires_at = models.DateTimeField()
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at", "-id"]

    def __str__(self):
        return f"licence for {self.company} ({self.seats} seats)"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at
