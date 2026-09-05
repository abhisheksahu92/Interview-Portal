"""The BGV business rules: order → consent → charge → vendor → report.

Only one place in this app moves money — :func:`charge_order`, called from
:func:`record_consent`. The ordering is deliberate and is the whole point of
the flow:

1. A recruiter *orders* a package. Nothing is billed; the order sits in
   ``CONSENT_PENDING`` and the candidate gets a tokenised consent link.
2. Cancelling before consent is free — no ledger row is ever written.
3. The candidate consents. Only then is the company charged, exactly once, via
   ``billing.ledger.add_charge(..., ref="bgv:<pk>")``. The ref makes the call
   idempotent, so a double-submitted consent form bills once.
4. The order is submitted to the vendor adapter. A vendor failure marks the
   order FAILED but **does not** reverse the charge automatically — refunds are
   a deliberate, human act, so a bug here can never silently zero revenue.
"""

import logging

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from bgv import gateway
from bgv.models import CheckPackage, VerificationOrder, money
from bgv.notify import notify

logger = logging.getLogger(__name__)

CONSENT_EVENT = "bgv_consent_requested"
COMPLETED_EVENT = "bgv_completed"


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #


def available_packages():
    return CheckPackage.objects.filter(active=True)


@transaction.atomic
def create_order(company, candidate, package, *, application=None, ordered_by=None, notify_candidate=True):
    """Raise a CONSENT_PENDING order and email the candidate their consent link.

    Both prices are snapshotted so a later re-price cannot restate this order.
    """
    order = VerificationOrder.objects.create(
        company=company,
        candidate=candidate,
        application=application,
        package=package,
        price_inr=money(package.price_inr),
        provider_cost_inr=money(package.provider_cost_inr),
        checks=list(package.checks or []),
        status=VerificationOrder.CONSENT_PENDING,
        provider=gateway.provider_name(),
        ordered_by=ordered_by,
        expires_at=VerificationOrder.default_expiry(),
    )
    if notify_candidate:
        transaction.on_commit(lambda: send_consent_request(order))
    return order


def consent_url(order):
    from django.conf import settings
    from django.urls import reverse

    path = reverse("bgv:consent", args=[order.token])
    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base else path


def send_consent_request(order):
    """Ask the candidate to consent. Never raises into the caller."""
    link = consent_url(order)
    body = (
        f"{order.company.name} would like to run a background check for "
        f"{order.job_title or 'a role'}.\n\n"
        f"Review what will be checked and give (or decline) consent here:\n{link}\n"
    )
    return notify(
        CONSENT_EVENT,
        order.candidate,
        {"order": order, "link": link, "company": order.company},
        company=order.company,
        subject=f"Consent needed: background check for {order.company.name}",
        body=body,
    )


@transaction.atomic
def cancel_order(order):
    """Cancel a not-yet-consented order. Free — no charge is ever raised."""
    if not order.can_cancel:
        return False
    order.status = VerificationOrder.CANCELLED
    order.revoked_at = order.revoked_at or timezone.now()
    order.save(update_fields=["status", "revoked_at", "updated_at"])
    return True


# --------------------------------------------------------------------------- #
# Consent and charging
# --------------------------------------------------------------------------- #


def charge_order(order):
    """Put this order's price on the company's next bill. Idempotent.

    Returns the ``BillingCharge`` (or ``None`` when billing is unavailable).
    ``ref`` is ``bgv:<pk>``, so calling twice updates one row rather than
    billing twice.
    """
    try:
        from billing import ledger
    except Exception as exc:  # pragma: no cover - billing is always installed
        logger.warning("bgv: billing ledger unavailable, order %s unbilled: %s", order.pk, exc)
        return None
    charge = ledger.add_charge(
        order.company,
        ledger.BGV,
        f"Background check — {order.candidate_name}",
        money(order.price_inr),
        ref=order.charge_reference,
        occurred_at=order.consent_given_at,
    )
    if charge is not None and order.charge_ref != order.charge_reference:
        order.charge_ref = order.charge_reference
        order.save(update_fields=["charge_ref", "updated_at"])
    return charge


@transaction.atomic
def record_consent(order, *, name, ip=None):
    """Record the candidate's consent, charge the company, submit to the vendor."""
    if order.consent_given_at is None:
        order.consent_given_at = timezone.now()
        order.consent_name = (name or "").strip()[:150]
        order.consent_ip = ip or None
        order.status = VerificationOrder.SUBMITTED
        order.last_used_at = order.consent_given_at
        order.save(
            update_fields=[
                "consent_given_at",
                "consent_name",
                "consent_ip",
                "status",
                "last_used_at",
                "updated_at",
            ]
        )
    charge_order(order)
    submit_to_provider(order)
    return order


def submit_to_provider(order):
    """Hand the consented order to the vendor adapter."""
    if order.provider_ref:
        return order.provider_ref
    provider = gateway.get_provider()
    try:
        ref = provider.submit(order)
    except gateway.NotConfigured as exc:
        logger.warning("bgv: provider not configured for order %s: %s", order.pk, exc)
        order.status = VerificationOrder.FAILED
        order.save(update_fields=["status", "updated_at"])
        return ""
    order.provider = provider.name
    order.provider_ref = ref or ""
    if order.status == VerificationOrder.CONSENT_PENDING:
        order.status = VerificationOrder.SUBMITTED
    order.save(update_fields=["provider", "provider_ref", "status", "updated_at"])
    return order.provider_ref


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


def apply_result(order, payload):
    """Apply a vendor status payload (poll or webhook) to ``order``.

    ``payload`` is ``{"state": <status>, "checks": {code: {status, notes}}}``.
    Completing an order generates its PDF report and notifies the recruiter.
    """
    state = (payload or {}).get("state") or ""
    checks = (payload or {}).get("checks") or {}
    fields = []
    if checks:
        merged = dict(order.result or {})
        for code, entry in checks.items():
            merged[code] = {
                "status": (entry or {}).get("status", ""),
                "notes": (entry or {}).get("notes", ""),
            }
        order.result = merged
        fields.append("result")
    if state and state != order.status:
        order.status = state
        fields.append("status")
    if state == VerificationOrder.COMPLETED and order.completed_at is None:
        order.completed_at = timezone.now()
        fields.append("completed_at")
    if fields:
        order.save(update_fields=[*fields, "updated_at"])
    if order.status == VerificationOrder.COMPLETED:
        build_report(order)
        send_completion_notice(order)
    return order


def build_report(order, force=False):
    """Render and attach the PDF report. Returns the file name, or ``""``."""
    if order.report_file and not force:
        return order.report_file.name
    from bgv.pdf import render_report_pdf

    content = render_report_pdf(order)
    if not content:
        return ""
    name = f"bgv-report-{order.pk}.pdf"
    order.report_file.save(name, ContentFile(content), save=False)
    order.save(update_fields=["report_file", "updated_at"])
    return order.report_file.name


def send_completion_notice(order):
    recipient = getattr(order.ordered_by, "email", "") or ""
    if not recipient:
        return ""
    return notify(
        COMPLETED_EVENT,
        recipient,
        {"order": order},
        company=order.company,
        subject=f"Background check complete — {order.candidate_name}",
        body=(
            f"The {order.package.name if order.package else 'background'} check for "
            f"{order.candidate_name} is complete"
            f"{' with discrepancies to review' if order.has_discrepancy else ' and all checks are clear'}."
        ),
    )


def poll_order(order):
    """Ask the vendor where ``order`` is and apply whatever comes back."""
    provider = gateway.get_provider()
    try:
        payload = provider.fetch_status(order)
    except gateway.NotConfigured as exc:
        logger.info("bgv: cannot poll order %s: %s", order.pk, exc)
        return order
    return apply_result(order, payload)


def pollable_orders(company=None):
    qs = VerificationOrder.objects.filter(
        status__in=(VerificationOrder.SUBMITTED, VerificationOrder.IN_PROGRESS)
    )
    return qs.for_company(company) if company is not None else qs


# --------------------------------------------------------------------------- #
# Margin (platform staff only)
# --------------------------------------------------------------------------- #


def margin_summary(company=None):
    """Revenue, vendor cost and margin over *charged* orders.

    Cancelled and never-consented orders are excluded: no money moved, so they
    are neither revenue nor cost.
    """
    orders = VerificationOrder.objects.billable()
    if company is not None:
        orders = orders.for_company(company)
    revenue = cost = money(0)
    count = 0
    for price, provider_cost in orders.values_list("price_inr", "provider_cost_inr"):
        revenue += money(price)
        cost += money(provider_cost)
        count += 1
    margin = revenue - cost
    percent = money(margin * 100 / revenue) if revenue > 0 else money(0)
    return {
        "count": count,
        "revenue": revenue,
        "cost": cost,
        "margin": margin,
        "margin_percent": percent,
    }


def margin_by_company():
    """Per-tenant margin rows, richest first — the /bgv/admin-margin/ table."""
    from core.models import Company

    rows = []
    for company in Company.objects.all():
        summary = margin_summary(company)
        if summary["count"]:
            rows.append({"company": company, **summary})
    rows.sort(key=lambda row: row["margin"], reverse=True)
    return rows
