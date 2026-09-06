def tenant(request):
    """Expose the active company and the user's role in it to templates."""
    company = getattr(request, "company", None)
    user = getattr(request, "user", None)
    role = user.role_in(company) if (user is not None and user.is_authenticated) else None
    companies = list(user.companies) if (user is not None and user.is_authenticated) else []
    return {
        "current_company": company,
        "current_role": role,
        "user_companies": companies,
    }


def analytics(request):
    """PostHog config, exposed only where tracking is appropriate.

    Deliberately limited to signed-in workspace users. The public side of this
    app is candidates: careers pages, assessments, offer signing and BGV
    consent. Loading a third-party tracker there would ship candidate activity
    to another processor without their consent, which is exactly what the DPDP
    Act is about. Recruiters are our own logged-in users, so product analytics
    on the workspace is a different question.
    """
    from django.conf import settings

    # "Signed in" was not enough: candidates sign in too, and the candidate
    # portal extends the same base template, so the tracker was loading for
    # exactly the people this docstring says it must not. Require a workspace
    # membership as well.
    user = getattr(request, "user", None)
    signed_in = bool(user and user.is_authenticated)
    is_workspace_user = (
        signed_in
        and not getattr(user, "is_candidate", False)
        and getattr(request, "company", None) is not None
    )
    enabled = bool(settings.POSTHOG_KEY) and is_workspace_user
    return {
        "posthog_key": settings.POSTHOG_KEY if enabled else "",
        "posthog_host": settings.POSTHOG_HOST,
    }
