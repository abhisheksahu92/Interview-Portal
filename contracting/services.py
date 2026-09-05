"""Contracting domain services: onboarding, engagements, timesheet lifecycle.

Views stay thin; every state change a recruiter, a contractor or a client can
make goes through a function here so the state machine is enforced in exactly
one place.
"""

import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from contracting import rates
from contracting.models import (
    ClientBillingProfile,
    Contractor,
    Engagement,
    OnboardingDocument,
    Timesheet,
)
from contracting.notify import notify

logger = logging.getLogger(__name__)


class InvalidTransition(Exception):
    """A timesheet was asked to make a move its state machine forbids."""

    def __init__(self, timesheet, target):
        self.timesheet = timesheet
        self.target = target
        super().__init__(
            f"A {timesheet.get_status_display().lower()} timesheet cannot become "
            f"{dict(Timesheet.STATUS_CHOICES)[target].lower()}."
        )


# --------------------------------------------------------------------------- #
# Onboarding
# --------------------------------------------------------------------------- #


CHECKLIST_FIELDS = (
    ("pan", "PAN number"),
    ("bank", "Bank details"),
)


def onboarding_checklist(contractor):
    """The rows shown on the contractor detail screen.

    Each row is ``{"key", "label", "done", "kind"}``; ``kind`` is ``"document"``
    for uploads and ``"field"`` for profile data. Documents count as done when
    uploaded and as verified separately, because a recruiter may collect a PAN
    card long before anyone checks it.
    """
    uploaded = contractor.document_kinds()
    verified = contractor.verified_kinds()
    rows = []
    for key, label in CHECKLIST_FIELDS:
        rows.append(
            {
                "key": key,
                "label": label,
                "kind": "field",
                "done": bool(getattr(contractor, key, None)),
                "verified": None,
            }
        )
    for kind, label in OnboardingDocument.KIND_CHOICES:
        if kind == OnboardingDocument.OTHER:
            continue
        rows.append(
            {
                "key": kind,
                "label": label,
                "kind": "document",
                "done": kind in uploaded,
                "verified": kind in verified,
            }
        )
    return rows


def onboarding_progress(contractor):
    """``{"done", "total", "percent", "complete", "missing"}`` for a contractor."""
    rows = onboarding_checklist(contractor)
    done = [row for row in rows if row["done"]]
    total = len(rows) or 1
    return {
        "done": len(done),
        "total": len(rows),
        "percent": int(round(len(done) * 100 / total)),
        "complete": len(done) == len(rows),
        "missing": [row["label"] for row in rows if not row["done"]],
    }


def is_onboarding_complete(contractor):
    return onboarding_progress(contractor)["complete"]


def activate_if_ready(contractor):
    """Flip an ONBOARDING contractor to ACTIVE once the checklist is complete."""
    if contractor.status == Contractor.ONBOARDING and is_onboarding_complete(contractor):
        contractor.status = Contractor.ACTIVE
        contractor.save(update_fields=["status", "updated_at"])
    return contractor


def add_document(contractor, kind, file, *, uploaded_by=None, note=""):
    """Attach an onboarding document and re-check the checklist."""
    document = OnboardingDocument.objects.create(
        contractor=contractor, kind=kind, file=file, uploaded_by=uploaded_by, note=note
    )
    activate_if_ready(contractor)
    return document


# --------------------------------------------------------------------------- #
# Engagements
# --------------------------------------------------------------------------- #


@transaction.atomic
def create_engagement(
    contractor,
    client,
    *,
    role_title,
    start,
    bill_rate_inr,
    pay_rate_inr,
    rate_unit=Engagement.HOUR,
    end=None,
    job=None,
    po_number="",
    tds_percent=None,
    status=Engagement.ACTIVE,
):
    """Place ``contractor`` with ``client`` and mark the contractor ACTIVE.

    Raises ``ValueError`` when the client belongs to a different tenant — an
    engagement is the join between two tenant-scoped rows and is the one place
    a cross-tenant mistake could leak data into an invoice.
    """
    if client.company_id != contractor.company_id:
        raise ValueError("Contractor and client must belong to the same company.")
    engagement = Engagement.objects.create(
        contractor=contractor,
        client=client,
        job=job,
        role_title=role_title,
        start=start,
        end=end,
        bill_rate_inr=bill_rate_inr,
        pay_rate_inr=pay_rate_inr,
        rate_unit=rate_unit,
        po_number=po_number or "",
        status=status,
        **({} if tds_percent is None else {"tds_percent": tds_percent}),
    )
    if contractor.status == Contractor.ONBOARDING and is_onboarding_complete(contractor):
        contractor.status = Contractor.ACTIVE
        contractor.save(update_fields=["status", "updated_at"])
    ClientBillingProfile.objects.get_or_create(
        client=client, defaults={"billing_email": client.contact_email}
    )
    return engagement


def end_engagement(engagement, end=None):
    engagement.end = end or timezone.localdate()
    engagement.status = Engagement.ENDED
    engagement.save(update_fields=["end", "status", "updated_at"])
    return engagement


# --------------------------------------------------------------------------- #
# Timesheet periods
# --------------------------------------------------------------------------- #


def week_bounds(day=None):
    """Monday–Sunday around ``day`` (defaults to today)."""
    day = day or timezone.localdate()
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def month_bounds(day=None):
    """First and last day of ``day``'s month."""
    day = day or timezone.localdate()
    start = day.replace(day=1)
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month - timedelta(days=1)


def month_start(value):
    """Normalise any date (or datetime) inside a month to its 1st."""
    if hasattr(value, "date") and not isinstance(value, date):
        value = value.date()
    return value.replace(day=1)


def blank_entries(period_start, period_end):
    """An empty grid covering every day of the period, for the weekly form."""
    entries = []
    day = period_start
    while day <= period_end:
        entries.append({"date": day.isoformat(), "hours": 0, "note": ""})
        day += timedelta(days=1)
    return entries


def get_or_create_timesheet(engagement, period_start=None, period_end=None):
    """The engagement's timesheet for a week, created as an empty DRAFT."""
    if period_start is None:
        period_start, period_end = week_bounds()
    elif period_end is None:
        period_end = period_start + timedelta(days=6)
    timesheet = Timesheet.objects.filter(
        engagement=engagement, period_start=period_start
    ).first()
    if timesheet is not None:
        return timesheet
    return Timesheet.objects.create(
        engagement=engagement,
        period_start=period_start,
        period_end=period_end,
        entries=[],
    )


# --------------------------------------------------------------------------- #
# Timesheet state machine
# --------------------------------------------------------------------------- #


def save_draft(timesheet, entries):
    """Store a contractor's grid without submitting it."""
    if not timesheet.is_editable:
        raise InvalidTransition(timesheet, Timesheet.DRAFT)
    timesheet.entries = entries
    timesheet.status = Timesheet.DRAFT
    timesheet.save(update_fields=["entries", "status", "updated_at"])
    return timesheet


def submit(timesheet, entries=None):
    """DRAFT/REJECTED → SUBMITTED and ping the client for approval."""
    if not timesheet.can_transition_to(Timesheet.SUBMITTED):
        raise InvalidTransition(timesheet, Timesheet.SUBMITTED)
    if entries is not None:
        timesheet.entries = entries
    timesheet.status = Timesheet.SUBMITTED
    timesheet.submitted_at = timezone.now()
    timesheet.client_note = ""
    timesheet.save(
        update_fields=["entries", "status", "submitted_at", "client_note", "updated_at"]
    )
    _notify_client_of_submission(timesheet)
    return timesheet


def approve(timesheet, *, access=None, user=None, note=""):
    """SUBMITTED → APPROVED, recording who approved it (client link or staff)."""
    if not timesheet.can_transition_to(Timesheet.APPROVED):
        raise InvalidTransition(timesheet, Timesheet.APPROVED)
    timesheet.status = Timesheet.APPROVED
    timesheet.approved_at = timezone.now()
    timesheet.approved_by_access = access
    timesheet.approved_by_user = user
    timesheet.client_note = note or ""
    timesheet.save(
        update_fields=[
            "status",
            "approved_at",
            "approved_by_access",
            "approved_by_user",
            "client_note",
            "updated_at",
        ]
    )
    _notify_contractor_of_decision(timesheet, "approved")
    return timesheet


def reject(timesheet, *, access=None, user=None, note=""):
    """SUBMITTED/APPROVED → REJECTED with a note the contractor can act on."""
    if not timesheet.can_transition_to(Timesheet.REJECTED):
        raise InvalidTransition(timesheet, Timesheet.REJECTED)
    timesheet.status = Timesheet.REJECTED
    timesheet.approved_at = None
    timesheet.approved_by_access = access
    timesheet.approved_by_user = user
    timesheet.client_note = note or ""
    timesheet.save(
        update_fields=[
            "status",
            "approved_at",
            "approved_by_access",
            "approved_by_user",
            "client_note",
            "updated_at",
        ]
    )
    _notify_contractor_of_decision(timesheet, "rejected")
    return timesheet


def mark_invoiced(timesheet, invoice):
    """APPROVED → INVOICED, pinning the timesheet to the invoice that billed it."""
    if not timesheet.can_transition_to(Timesheet.INVOICED):
        raise InvalidTransition(timesheet, Timesheet.INVOICED)
    timesheet.status = Timesheet.INVOICED
    timesheet.client_invoice = invoice
    timesheet.save(update_fields=["status", "client_invoice", "updated_at"])
    return timesheet


def timesheet_totals(timesheet):
    """Bill/pay/margin for one timesheet, for the queue and margin screens."""
    bill = rates.bill_amount(timesheet)
    pay = rates.pay_amount(timesheet)
    return {
        "quantity": rates.quantity(timesheet),
        "unit_label": rates.unit_label(timesheet.engagement.rate_unit),
        "bill": bill,
        "pay": pay,
        "margin": bill - pay,
    }


# --------------------------------------------------------------------------- #
# Notifications (never fatal)
# --------------------------------------------------------------------------- #


def _notify_client_of_submission(timesheet):
    engagement = timesheet.engagement
    recipients = {
        access.email for access in engagement.client.accesses.all() if access.is_active
    }
    profile = ClientBillingProfile.objects.filter(client=engagement.client).first()
    if profile and profile.billing_email:
        recipients.add(profile.billing_email)
    if not recipients and engagement.client.contact_email:
        recipients.add(engagement.client.contact_email)
    period = f"{timesheet.period_start:%d %b} – {timesheet.period_end:%d %b %Y}"
    for email in sorted(recipients):
        notify(
            "timesheet_submitted",
            email,
            {
                "contractor_name": engagement.contractor.name,
                "client_name": engagement.client.name,
                "period": period,
                "total_hours": str(timesheet.total_hours),
            },
            company=engagement.contractor.company,
            subject=f"Timesheet to approve: {engagement.contractor.name} ({period})",
            body=(
                f"{engagement.contractor.name} submitted {timesheet.total_hours} hours "
                f"for {period} on {engagement.role_title}.\n\n"
                "Open your client portal link to approve or reject it."
            ),
        )


def _notify_contractor_of_decision(timesheet, decision):
    contractor = timesheet.engagement.contractor
    if not contractor.email:
        return
    period = f"{timesheet.period_start:%d %b} – {timesheet.period_end:%d %b %Y}"
    notify(
        f"timesheet_{decision}",
        contractor.email,
        {
            "contractor_name": contractor.name,
            "period": period,
            "decision": decision,
            "note": timesheet.client_note,
        },
        company=contractor.company,
        subject=f"Your timesheet for {period} was {decision}",
        body=(
            f"Hello {contractor.name},\n\nYour timesheet for {period} was {decision}."
            + (f"\n\nNote: {timesheet.client_note}" if timesheet.client_note else "")
        ),
    )
