"""Billing models: plans, subscriptions, usage, invoices and placement fees."""

import math
from decimal import Decimal

from django.db import models
from django.utils import timezone


class Plan(models.Model):
    """A subscription tier. Seeded by data migrations."""

    FREE = "FREE"
    PRO = "PRO"  # legacy tier, kept for existing subscriptions
    STARTER = "STARTER"
    GROWTH = "GROWTH"
    AGENCY = "AGENCY"
    CODE_CHOICES = [
        (FREE, "Free"),
        (STARTER, "Starter"),
        (GROWTH, "Growth"),
        (AGENCY, "Agency"),
        (PRO, "Pro (legacy)"),
    ]
    PAID_CODES = (STARTER, GROWTH, AGENCY)

    code = models.CharField(max_length=20, choices=CODE_CHOICES, unique=True)
    name = models.CharField(max_length=80)
    max_open_jobs = models.PositiveIntegerField(default=1)
    max_seats = models.PositiveIntegerField(default=2)
    ai_credits_monthly = models.PositiveIntegerField(default=0)
    stripe_price_id = models.CharField(max_length=120, blank=True)
    razorpay_plan_id_monthly = models.CharField(max_length=120, blank=True)
    razorpay_plan_id_yearly = models.CharField(max_length=120, blank=True)
    price_monthly = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    price_monthly_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_yearly_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    per_hire_fee_inr = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    # Entitlement flags read via billing.entitlements.has_feature().
    features = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["price_monthly_inr", "price_monthly"]

    def __str__(self):
        return self.name

    @property
    def is_free(self):
        return self.code == self.FREE

    def price_for(self, interval):
        """INR price for MONTHLY/YEARLY."""
        if interval == Subscription.YEARLY:
            return self.price_yearly_inr
        return self.price_monthly_inr

    def razorpay_plan_id(self, interval):
        if interval == Subscription.YEARLY:
            return self.razorpay_plan_id_yearly
        return self.razorpay_plan_id_monthly


class Subscription(models.Model):
    """One company's current plan, provider state and billing identity."""

    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"
    TRIALING = "TRIALING"
    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (PAST_DUE, "Past due"),
        (CANCELED, "Canceled"),
        (TRIALING, "Trialing"),
    ]

    STRIPE = "STRIPE"
    RAZORPAY = "RAZORPAY"
    PROVIDER_CHOICES = [(STRIPE, "Stripe"), (RAZORPAY, "Razorpay")]

    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    INTERVAL_CHOICES = [(MONTHLY, "Monthly"), (YEARLY, "Yearly")]

    TRIAL_DAYS = 14

    company = models.OneToOneField(
        "core.Company", on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    provider = models.CharField(
        max_length=20, choices=PROVIDER_CHOICES, default=RAZORPAY, blank=True
    )
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default=MONTHLY)
    stripe_customer_id = models.CharField(max_length=120, blank=True)
    stripe_subscription_id = models.CharField(max_length=120, blank=True)
    razorpay_customer_id = models.CharField(max_length=120, blank=True)
    razorpay_subscription_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    past_due_since = models.DateTimeField(null=True, blank=True)
    gstin = models.CharField(max_length=20, blank=True)
    billing_address = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company__name"]

    def __str__(self):
        return f"{self.company} — {self.plan}"

    @property
    def is_usable(self):
        """A subscription still entitled to its plan limits."""
        return self.status in {self.ACTIVE, self.TRIALING, self.PAST_DUE}

    @property
    def in_trial(self):
        """True while the 14-day full-featured trial is still running."""
        return bool(self.trial_ends_at and self.trial_ends_at > timezone.now())

    @property
    def trial_days_left(self):
        if not self.in_trial:
            return 0
        delta = self.trial_ends_at - timezone.now()
        return max(0, math.ceil(delta.total_seconds() / 86400))

    @property
    def is_paid(self):
        return not self.plan.is_free and self.is_usable

    @property
    def seats_used(self):
        from core.models import Membership

        return Membership.objects.filter(company_id=self.company_id).count()

    @property
    def max_seats(self):
        from billing.entitlements import plan_for

        return plan_for(self.company).max_seats

    @property
    def max_open_jobs(self):
        if not self.is_usable:
            from billing.services import free_plan

            return free_plan().max_open_jobs
        return self.plan.max_open_jobs

    @property
    def billing_state_code(self):
        return str((self.billing_address or {}).get("state_code") or "").strip()


class UsageRecord(models.Model):
    """One metered event (or batch of events) inside a monthly period."""

    AI_SCREEN = "AI_SCREEN"
    WHATSAPP_MSG = "WHATSAPP_MSG"
    VIDEO_MINUTE = "VIDEO_MINUTE"
    KIND_CHOICES = [
        (AI_SCREEN, "AI screening"),
        (WHATSAPP_MSG, "WhatsApp message"),
        (VIDEO_MINUTE, "Video minute"),
    ]

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="usage_records"
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    quantity = models.PositiveIntegerField(default=1)
    period_start = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "kind", "period_start"])]

    def __str__(self):
        return f"{self.company_id} {self.kind} x{self.quantity}"


class Invoice(models.Model):
    """A GST invoice, numbered sequentially per Indian financial year."""

    GST_RATE = Decimal("18.00")

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="invoices"
    )
    number = models.CharField(max_length=40, unique=True)
    fy = models.CharField(max_length=10, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=GST_RATE)
    cgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gstin = models.CharField(max_length=20, blank=True)
    place_of_supply = models.CharField(max_length=4, blank=True)
    description = models.CharField(max_length=200, blank=True)
    pdf = models.FileField(upload_to="invoices/", blank=True)
    provider = models.CharField(
        max_length=20, choices=Subscription.PROVIDER_CHOICES, blank=True
    )
    provider_ref = models.CharField(max_length=120, blank=True)
    issued_at = models.DateTimeField(default=timezone.now)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at", "-id"]

    def __str__(self):
        return self.number

    @property
    def tax_total(self):
        return self.cgst + self.sgst + self.igst

    @property
    def is_intra_state(self):
        return self.cgst > 0 or self.sgst > 0


class DunningReminder(models.Model):
    """A reminder already sent for a past-due subscription (idempotency guard)."""

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="dunning_reminders"
    )
    day = models.PositiveSmallIntegerField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["day"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "day"], name="billing_dunning_unique_day"
            )
        ]

    def __str__(self):
        return f"{self.subscription_id} day {self.day}"


class PlacementFee(models.Model):
    """Per-hire success fee, created when an application is marked HIRED."""

    PENDING = "PENDING"
    INVOICED = "INVOICED"
    PAID = "PAID"
    WAIVED = "WAIVED"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (INVOICED, "Invoiced"),
        (PAID, "Paid"),
        (WAIVED, "Waived"),
    ]

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="placement_fees"
    )
    application = models.OneToOneField(
        "jobs.Application", on_delete=models.CASCADE, related_name="placement_fee"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name="placement_fees"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company} placement fee ₹{self.amount}"
