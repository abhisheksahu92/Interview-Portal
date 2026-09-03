"""Branding resolution for a company (used by templates and outbound email)."""

import re
from dataclasses import dataclass

DEFAULT_BRAND_NAME = "Interview Portal"
DEFAULT_BRAND_COLOR = "#4f46e5"

# Colours land in a CSS custom property, so only safe literals are accepted.
_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$|^[a-zA-Z]{3,20}$")


def safe_color(value):
    """Return ``value`` when it is a safe CSS colour literal, else the default."""
    value = (value or "").strip()
    if value and _COLOR_RE.match(value):
        return value
    return DEFAULT_BRAND_COLOR


@dataclass(frozen=True)
class Brand:
    """The effective branding for one company (or the product default)."""

    name: str = DEFAULT_BRAND_NAME
    logo_url: str = ""
    color: str = DEFAULT_BRAND_COLOR
    hide_powered_by: bool = False
    email_from_name: str = DEFAULT_BRAND_NAME
    custom_domain: str = ""
    is_custom: bool = False

    @property
    def powered_by(self):
        """Footer line, or "" when the partner hides it."""
        if self.hide_powered_by:
            return ""
        return f"Powered by {DEFAULT_BRAND_NAME}"


DEFAULT_BRAND = Brand()


def brand_for(company):
    """Effective :class:`Brand` for ``company``; the default brand when unbranded.

    Safe to call with ``None`` and before the partners tables exist.
    """
    if company is None:
        return DEFAULT_BRAND
    white_label = _white_label(company)
    if white_label is None:
        return DEFAULT_BRAND
    logo_url = ""
    if white_label.logo:
        try:
            logo_url = white_label.logo.url
        except Exception:  # pragma: no cover - storage may be unavailable
            logo_url = ""
    name = white_label.brand_name or DEFAULT_BRAND_NAME
    return Brand(
        name=name,
        logo_url=logo_url,
        color=safe_color(white_label.primary_color),
        hide_powered_by=white_label.hide_powered_by,
        email_from_name=white_label.email_from_name or name,
        custom_domain=white_label.custom_domain,
        is_custom=True,
    )


def _white_label(company):
    from partners.models import WhiteLabel

    try:
        return WhiteLabel.objects.filter(company=company).first()
    except Exception:  # pragma: no cover - table missing during early migrate
        return None
