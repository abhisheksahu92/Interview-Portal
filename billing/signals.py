"""Enforce plan limits on jobs without touching the jobs app."""

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from billing.limits import can_open_job
from billing.models import PlacementFee, Subscription
from billing.services import free_plan, trial_end_from


@receiver(pre_save, sender="jobs.Job", dispatch_uid="billing_job_open_limit")
def enforce_open_job_limit(sender, instance, raw=False, **kwargs):
    """Block a job transitioning into OPEN beyond the company's plan limit.

    Only *metered* companies are checked: a company is metered once it has a
    ``Subscription`` row (created on its first visit to the billing page, by
    ``manage.py provision_subscriptions``, or by a Stripe checkout). Companies
    with no billing record yet — fixtures, demo seeds, imports — are left alone
    so enforcement can never break data that predates billing.
    """
    if raw or instance.status != sender.OPEN or instance.company_id is None:
        return

    if not Subscription.objects.filter(company_id=instance.company_id).exists():
        return

    if instance.pk:
        previous_status = (
            sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
        if previous_status == sender.OPEN:
            return  # already open: saving other fields must never be blocked

    allowed, reason = can_open_job(instance.company, exclude_pk=instance.pk)
    if not allowed:
        raise ValidationError({"status": reason})


@receiver(post_save, sender="core.Company", dispatch_uid="billing_company_subscription")
def provision_company_subscription(sender, instance, created, raw=False, **kwargs):
    """Give every new company a 14-day full-featured trial subscription.

    The row is billed on FREE, but ``billing.entitlements.plan_for`` returns the
    trial tier (AGENCY) until ``trial_ends_at`` passes, so both the paid features
    *and* the trial tier's limits apply until the trial expires, at which point
    the company falls back to FREE.

    ``manage.py provision_subscriptions`` remains the backfill path for companies
    created before billing existed (or by ``loaddata``, which sets ``raw``).
    """
    if raw or not created:
        return
    if Subscription.objects.filter(company_id=instance.pk).exists():
        return
    Subscription.objects.create(
        company_id=instance.pk,
        plan=free_plan(),
        status=Subscription.TRIALING,
        trial_ends_at=trial_end_from(),
    )


@receiver(post_save, sender="jobs.Application", dispatch_uid="billing_placement_fee")
def create_placement_fee(sender, instance, raw=False, **kwargs):
    """Charge a per-hire success fee when an application reaches HIRED."""
    if raw or instance.status != sender.HIRED:
        return
    from billing.entitlements import plan_for

    company = instance.job.company
    plan = plan_for(company)
    fee = getattr(plan, "per_hire_fee_inr", None)
    if not fee:
        return
    PlacementFee.objects.get_or_create(
        application=instance,
        defaults={"company": company, "amount": fee, "status": PlacementFee.PENDING},
    )
