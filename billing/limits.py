"""Plan enforcement: how many jobs a company may keep open."""

from billing.services import get_subscription, open_job_count


class JobLimitExceeded(Exception):
    """Raised when opening a job would exceed the company's plan limit."""


def can_open_job(company, exclude_pk=None):
    """Return ``(allowed, reason)`` for opening one more job at ``company``.

    A company inside its post-trial grace window (``Subscription.grace_until``,
    set by ``expire_trials``) is never blocked: it has just been downgraded and
    gets a week to pick a plan or close jobs before limits bite.
    """
    if company is None:
        return False, "No company selected."
    subscription = get_subscription(company)
    if subscription.in_grace:
        return True, ""
    plan = subscription.effective_plan
    limit = plan.max_open_jobs
    used = open_job_count(company, exclude_pk=exclude_pk)
    if used >= limit:
        return False, (
            f"Your {plan.name} plan allows {limit} open "
            f"job{'' if limit == 1 else 's'} and you already have {used}. "
            "Upgrade your plan or close a job first."
        )
    return True, ""


def usage(company):
    """Overview numbers for the billing page."""
    subscription = get_subscription(company)
    used = open_job_count(company)
    limit = subscription.max_open_jobs
    return {
        "subscription": subscription,
        "in_grace": subscription.in_grace,
        "grace_until": subscription.grace_until,
        "plan": subscription.effective_plan,
        "open_jobs": used,
        "max_open_jobs": limit,
        "remaining": max(limit - used, 0),
        "at_limit": used >= limit and not subscription.in_grace,
    }
