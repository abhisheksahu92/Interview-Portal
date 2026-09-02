"""Enforce plan limits on jobs without touching the jobs app."""

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver

from billing.limits import can_open_job
from billing.models import Subscription


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
