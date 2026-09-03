"""Safe placeholder substitution for recruiter-authored offer bodies.

Offer templates are written by tenant users, so they are **never** handed to the
Django template engine — that would expose every filter, tag and attribute walk
in the process to whoever can edit a template. Instead a single regex replaces a
fixed whitelist of ``{{placeholder}}`` names (plus ``{{custom.<key>}}``) with
HTML-escaped values. Anything else — ``{% load %}``, ``{{ settings.SECRET_KEY }}``,
unknown names — is left untouched as literal text.
"""

import re
from decimal import Decimal

from django.utils.html import escape

#: The placeholder names a template may use, with recruiter-facing help text.
PLACEHOLDERS = (
    ("candidate_name", "Candidate's full name"),
    ("candidate_email", "Candidate's email address"),
    ("job_title", "Job title"),
    ("company_name", "Your company name"),
    ("salary", "Offered salary, formatted"),
    ("currency", "Salary currency code"),
    ("joining_date", "Proposed joining date"),
    ("expires_at", "Offer expiry date"),
    ("location", "Job location"),
    ("custom.*", "Any custom field you add to the offer, e.g. {{custom.bonus}}"),
)

PLACEHOLDER_NAMES = tuple(name for name, _ in PLACEHOLDERS if name != "custom.*")

_TOKEN_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_-]+)*)\s*\}\}")

_CUSTOM_PREFIX = "custom."


def _stringify(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return f"{int(normalized):,}"
        return f"{normalized:,f}"
    return str(value)


def resolve(name, context):
    """Value for placeholder ``name``, or None when it is not whitelisted/known."""
    context = context or {}
    if name.startswith(_CUSTOM_PREFIX):
        key = name[len(_CUSTOM_PREFIX) :]
        custom = context.get("custom") or {}
        if not isinstance(custom, dict) or key not in custom:
            return None
        return custom[key]
    if name not in PLACEHOLDER_NAMES:
        return None
    return context.get(name)


def render_body(body, context, escape_values=True):
    """Substitute whitelisted placeholders in ``body``.

    Unknown or unsafe-looking tokens are preserved verbatim so a bad template is
    obvious to the author instead of silently leaking or executing anything.
    """
    if not body:
        return ""

    def _sub(match):
        value = resolve(match.group(1), context)
        if value is None:
            return match.group(0)
        text = _stringify(value)
        return escape(text) if escape_values else text

    return _TOKEN_RE.sub(_sub, str(body))


def offer_context(offer):
    """The placeholder context for a saved (or unsaved) :class:`~offers.models.Offer`."""
    application = offer.application
    job = application.job
    user = application.candidate.user
    name = (user.get_full_name() or "").strip() or user.email
    location = job.location or ""
    custom = offer.custom_fields if isinstance(offer.custom_fields, dict) else {}
    return {
        "candidate_name": name,
        "candidate_email": user.email,
        "job_title": job.title,
        "company_name": job.company.name,
        "salary": offer.salary,
        "currency": offer.currency,
        "joining_date": offer.joining_date.strftime("%d %b %Y") if offer.joining_date else "",
        "expires_at": offer.expires_at.strftime("%d %b %Y") if offer.expires_at else "",
        "location": f" ({location})" if location else "",
        "custom": custom,
    }


def sample_context(company=None):
    """Placeholder values for the template preview screen."""
    return {
        "candidate_name": "Asha Rao",
        "candidate_email": "asha@example.com",
        "job_title": "Senior Python Engineer",
        "company_name": getattr(company, "name", "Your Company"),
        "salary": Decimal("1800000"),
        "currency": "INR",
        "joining_date": "01 Apr 2026",
        "expires_at": "15 Mar 2026",
        "location": " (Bengaluru)",
        "custom": {"bonus": "10% annual", "reporting_to": "VP Engineering"},
    }
