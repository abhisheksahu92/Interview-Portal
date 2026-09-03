"""Attach a referral to a company as soon as its OWNER membership is created."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Membership


@receiver(post_save, sender=Membership, dispatch_uid="partners_attach_referral")
def attach_referral_on_owner(sender, instance, created, **kwargs):
    if not created or instance.role != Membership.OWNER:
        return
    from partners.middleware import current_ref
    from partners.referral import attach_referral

    code = current_ref()
    if not code:
        return
    attach_referral(instance.company, code=code)
