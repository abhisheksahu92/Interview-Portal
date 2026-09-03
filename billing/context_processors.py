"""Expose the active company's plan to every template (for the nav badge)."""

from billing.models import Subscription


def billing(request):
    company = getattr(request, "company", None)
    if company is None or not getattr(request.user, "is_authenticated", False):
        return {}
    subscription = (
        Subscription.objects.filter(company=company).select_related("plan").first()
    )
    if subscription is None:
        return {"billing_subscription": None, "billing_plan": None,
                "billing_effective_plan": None, "billing_in_trial": False,
                "billing_trial_days_left": 0}
    # The badge must show what the company can actually *use* right now, which
    # during the trial is the AGENCY tier rather than the billed FREE plan.
    effective_plan = subscription.effective_plan
    return {
        "billing_subscription": subscription,
        "billing_plan": subscription.plan,
        "billing_effective_plan": effective_plan,
        "billing_in_trial": subscription.in_trial,
        "billing_trial_days_left": subscription.trial_days_left,
    }
