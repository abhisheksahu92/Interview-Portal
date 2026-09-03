"""``{% load features %}`` — plan-entitlement tags for templates.

Two ways to ask whether the current tenant's plan includes a paid feature::

    {% load features %}

    {% feature_enabled "video" as can_video %}
    {% if can_video %}...{% endif %}

    {% if company|has_feature:"video" %}...{% endif %}

``{% feature_enabled %}`` resolves the company from the template context
(``request.company``, set by ``core.middleware.TenantMiddleware``, falling back
to ``current_company``) unless one is passed explicitly. The filter always takes
the company as its left-hand side. Both are read-only and never raise: an
anonymous visitor or a missing company simply has no features.
"""

from django import template

from billing.entitlements import has_feature as _has_feature

register = template.Library()


def _company_from(context):
    request = context.get("request")
    company = getattr(request, "company", None)
    if company is None:
        company = context.get("current_company")
    return company


@register.simple_tag(takes_context=True)
def feature_enabled(context, name, company=None):
    """True when the active company's plan enables the ``name`` feature."""
    if company is None:
        company = _company_from(context)
    return _has_feature(company, name)


@register.filter(name="has_feature")
def has_feature(company, name):
    """Filter form: ``{% if company|has_feature:"offers" %}``."""
    return _has_feature(company, name)
