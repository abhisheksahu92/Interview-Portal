"""``{% load whitelabel %}`` — branding tags used by the base template.

Each tag resolves the active company from the template context
(``current_company``, set by ``core.context_processors.tenant``) unless one is
passed explicitly, and falls back to the product default when the company has
no :class:`partners.models.WhiteLabel` row.
"""

from django import template
from django.utils.safestring import mark_safe

from partners.whitelabel import brand_for

register = template.Library()


def _brand(context, company=None):
    if company is None:
        company = context.get("current_company") or getattr(
            context.get("request"), "company", None
        )
    return brand_for(company)


@register.simple_tag(takes_context=True)
def brand_name(context, company=None):
    """The company's brand name, or "Interview Portal"."""
    return _brand(context, company).name


@register.simple_tag(takes_context=True)
def brand_logo_url(context, company=None):
    """URL of the company's logo, or "" when it has none."""
    return _brand(context, company).logo_url


@register.simple_tag(takes_context=True)
def brand_color(context, company=None):
    """The brand's primary colour (hex)."""
    return _brand(context, company).color


@register.simple_tag(takes_context=True)
def brand_style(context, company=None):
    """A ``<style>`` block overriding the brand CSS variable, or "" if default."""
    brand = _brand(context, company)
    if not brand.is_custom:
        return ""
    color = brand.color
    return mark_safe(  # noqa: S308 - colour comes from a validated model field
        "<style>:root,[data-bs-theme=dark]{"
        f"--ip-brand:{color};--ip-accent:{color};--bs-primary:{color};"
        "}</style>"
    )


@register.simple_tag(takes_context=True)
def powered_by(context, company=None):
    """"Powered by Interview Portal", or "" when the partner hides it."""
    return _brand(context, company).powered_by
