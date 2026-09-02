"""Expose the active company's plan to every template (for the nav badge)."""

from billing.models import Subscription


def billing(request):
    company = getattr(request, "company", None)
    if company is None or not getattr(request.user, "is_authenticated", False):
        return {}
    subscription = (
        Subscription.objects.filter(company=company).select_related("plan").first()
    )
    return {
        "billing_subscription": subscription,
        "billing_plan": subscription.plan if subscription else None,
    }
