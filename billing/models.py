"""Billing models: plans and per-company subscriptions."""

from django.db import models


class Plan(models.Model):
    """A subscription tier. Seeded by a data migration (FREE / PRO)."""

    FREE = "FREE"
    PRO = "PRO"
    CODE_CHOICES = [
        (FREE, "Free"),
        (PRO, "Pro"),
    ]

    code = models.CharField(max_length=20, choices=CODE_CHOICES, unique=True)
    name = models.CharField(max_length=80)
    max_open_jobs = models.PositiveIntegerField(default=1)
    stripe_price_id = models.CharField(max_length=120, blank=True)
    price_monthly = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    # Entitlement flags read via billing.entitlements.has_feature().
    features = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["price_monthly"]

    def __str__(self):
        return self.name

    @property
    def is_free(self):
        return self.code == self.FREE


class Subscription(models.Model):
    """One company's current plan and Stripe state."""

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

    company = models.OneToOneField(
        "core.Company", on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    stripe_customer_id = models.CharField(max_length=120, blank=True)
    stripe_subscription_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    current_period_end = models.DateTimeField(null=True, blank=True)
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
    def max_open_jobs(self):
        if not self.is_usable:
            from billing.services import free_plan

            return free_plan().max_open_jobs
        return self.plan.max_open_jobs
