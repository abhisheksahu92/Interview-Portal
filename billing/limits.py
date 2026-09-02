"""Plan enforcement: how many jobs a company may keep open."""

from billing.services import get_subscription, open_job_count


class JobLimitExceeded(Exception):
    """Raised when opening a job would exceed the company's plan limit."""


def can_open_job(company, exclude_pk=None):
    """Return ``(allowed, reason)`` for opening one more job at ``company``."""
    if company is None:
        return False, "No company selected."
    subscription = get_subscription(company)
    limit = subscription.max_open_jobs
    used = open_job_count(company, exclude_pk=exclude_pk)
    if used >= limit:
        return False, (
            f"Your {subscription.plan.name} plan allows {limit} open "
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
        "plan": subscription.plan,
        "open_jobs": used,
        "max_open_jobs": limit,
        "remaining": max(limit - used, 0),
        "at_limit": used >= limit,
    }
