"""Feature entitlements derived from a company's plan.

The single seam every Phase 3 app uses to decide whether a paid feature is
available to the current tenant::

    from billing.entitlements import FeatureRequiredMixin, has_feature, require_feature

    if has_feature(request.company, "client_portal"): ...

    @require_feature("scheduling")
    def my_view(request): ...

    class MyView(FeatureRequiredMixin, TemplateView):
        required_feature = "scheduling"

Flags live in ``Plan.features`` (a JSON dict). A company with no Subscription
row falls back to the FREE plan, and an unusable subscription (CANCELED) loses
its paid flags. Companies inside their 14-day trial get the full AGENCY flag
set until ``Subscription.trial_ends_at`` passes.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

# Known feature flags. Feature agents read these names; PRO grants them all.
FEATURES = (
    "scheduling",
    "careers_page",
    "client_portal",
    "whatsapp",
    "video",
    "api",
    "talent_pool_search",
    "ai_extraction",
    "offers",
    "analytics",
    "marketplace",
    "white_label",
    "integrations",
    "contracting",
    "exchange",
)

#: Human-readable names for the flags above, for plan cards and gate messages.
FEATURE_LABELS = {
    "scheduling": "Interview scheduling",
    "careers_page": "Careers page",
    "client_portal": "Client portal",
    "whatsapp": "WhatsApp updates",
    "video": "Video screening",
    "api": "REST API access",
    "talent_pool_search": "Verified talent pool",
    "ai_extraction": "AI résumé extraction",
    "offers": "Offer letters and e-sign",
    "analytics": "Analytics",
    "marketplace": "Question marketplace",
    "white_label": "White-label branding",
    "integrations": "Webhooks and integrations",
    "contracting": "Contracting back office",
    "exchange": "Agency requirement exchange",
}


def feature_label(name):
    """A human-readable name for a feature flag."""
    key = str(name or "").strip()
    return FEATURE_LABELS.get(key, key.replace("_", " ").capitalize())


class FeatureNotAvailable(PermissionDenied):
    """The current company's plan does not include the requested feature."""

    def __init__(self, name):
        self.feature = name
        super().__init__(f"Your plan does not include the '{name}' feature.")


def plan_for(company):
    """The Plan governing ``company``, or None when it cannot be determined.

    Honours the 14-day trial: a company whose subscription is still TRIALING
    inside its trial window is entitled to the full trial tier (AGENCY),
    whatever tier it is billed on. Once the trial has expired the billed tier
    applies — STARTER for companies provisioned from phase 4 on, FREE for
    legacy rows and cancelled subscriptions.
    """
    if company is None:
        return None
    subscription = getattr(company, "subscription", None)
    if subscription is not None:
        if subscription.in_trial and subscription.status == subscription.TRIALING:
            from billing.services import trial_plan

            return trial_plan()
        if subscription.is_usable:
            return subscription.plan
    from billing.services import free_plan

    return free_plan()


def has_feature(company, name) -> bool:
    """True when ``company``'s plan enables the ``name`` feature flag."""
    plan = plan_for(company)
    if plan is None:
        return False
    return bool((plan.features or {}).get(name, False))


def require_feature(name):
    """View decorator: 402-style gate raising PermissionDenied when unavailable."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not has_feature(getattr(request, "company", None), name):
                raise FeatureNotAvailable(name)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


class FeatureRequiredMixin:
    """CBV counterpart of :func:`require_feature`; set ``required_feature``."""

    required_feature = None

    def dispatch(self, request, *args, **kwargs):
        name = self.required_feature
        if name and not has_feature(getattr(request, "company", None), name):
            raise FeatureNotAvailable(name)
        return super().dispatch(request, *args, **kwargs)
