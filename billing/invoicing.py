"""GST invoicing: FY numbering, tax split, monthly bill assembly and PDFs.

The monthly bill is assembled from four sources, in this order::

    SUBSCRIPTION  the plan fee — seats_used x price for a SEAT plan (STARTER),
                  a single flat line for GROWTH/AGENCY
    SUCCESS_FEE   one line per PlacementFee raised in the period
    AI_OVERAGE    AI screens beyond plan.ai_included x plan.ai_overage_inr
    <other>       BillingCharge rows pushed in by sibling apps through
                  billing.ledger.add_charge (BGV, platform fees, ...)

``build_monthly_invoice(company, year, month)`` persists that as one Invoice
per company per period (idempotent), and ``projected_bill(company)`` renders
the same lines for the running month without writing anything.
"""

import calendar
import logging
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from billing.models import (
    Invoice,
    InvoiceCounter,
    PlacementFee,
    Plan,
    Subscription,
    UsageRecord,
)

logger = logging.getLogger(__name__)

NUMBER_PREFIX = "IP"
TWO = Decimal("0.01")


def financial_year(moment=None):
    """Indian FY label for ``moment`` — 2026-04-01 → ``2026-27``."""
    moment = moment or timezone.now()
    date = getattr(moment, "date", lambda: moment)()
    year = date.year if date.month >= 4 else date.year - 1
    return f"{year}-{(year + 1) % 100:02d}"


def next_number(moment=None, fy=None):
    """Allocate the next invoice number for the FY, e.g. ``IP/2026-27/0001``.

    The FY counter row is locked with ``SELECT ... FOR UPDATE`` inside a
    transaction, so concurrent payments queue up instead of racing for the same
    sequence number (the old "read the highest existing number" scan could hand
    the same number to two writers). SQLite has no row locks but serialises
    writers with a whole-database write lock, which gives the same guarantee —
    ``select_for_update`` is simply a no-op there, so the code path is identical.

    Note this *consumes* a number; use :func:`peek_number` for a read-only look.
    """
    fy = fy or financial_year(moment)
    with transaction.atomic():
        counter = InvoiceCounter.objects.select_for_update().filter(fy=fy).first()
        if counter is None:
            # Another writer may create the row first; create-then-lock.
            InvoiceCounter.objects.get_or_create(fy=fy, defaults={"last_seq": 0})
            counter = InvoiceCounter.objects.select_for_update().get(fy=fy)
        counter.last_seq += 1
        counter.save(update_fields=["last_seq", "updated_at"])
        seq = counter.last_seq
    return f"{NUMBER_PREFIX}/{fy}/{seq:04d}"


def peek_number(moment=None, fy=None):
    """The number :func:`next_number` would hand out next, without taking it."""
    fy = fy or financial_year(moment)
    counter = InvoiceCounter.objects.filter(fy=fy).first()
    seq = (counter.last_seq if counter else 0) + 1
    return f"{NUMBER_PREFIX}/{fy}/{seq:04d}"


def _q(value):
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


def company_state_code(company):
    """The GST state code of ``company`` as a *seller* — "" when unknown.

    Read from the tenant's own ``Subscription.billing_address["state_code"]``,
    falling back to the first two digits of its GSTIN (which encode the state).
    """
    if company is None:
        return ""
    subscription = getattr(company, "subscription", None)
    if subscription is None:
        from billing.models import Subscription

        subscription = Subscription.objects.filter(company=company).first()
    if subscription is None:
        return ""
    code = str((subscription.billing_address or {}).get("state_code") or "").strip()
    if code:
        return code
    gstin = str(subscription.gstin or "").strip()
    head = gstin[:2]
    return head if head.isdigit() else ""


def gst_split(amount, state_code, rate=Invoice.GST_RATE, home_state_code=None):
    """Split ``amount`` into (cgst, sgst, igst) for a customer state code.

    Intra-state (customer state == the *seller's* state) is split into equal
    CGST/SGST halves; anything else — including an unknown state on either
    side — is IGST.

    ``home_state_code`` is the seller's state. Platform invoices leave it
    ``None`` and fall back to ``settings.COMPANY_STATE_CODE`` (the platform
    operator); a tenant invoicing its own client passes *its* state code, via
    :func:`company_state_code`, so the split follows that tenant's place of
    supply and not the operator's.
    """
    amount = Decimal(amount or 0)
    tax = _q(amount * Decimal(rate) / Decimal(100))
    if home_state_code is None:
        home = str(getattr(settings, "COMPANY_STATE_CODE", "") or "").strip()
    else:
        home = str(home_state_code or "").strip()
    customer = str(state_code or "").strip()
    if home and customer and customer == home:
        half = _q(tax / 2)
        return half, _q(tax - half), Decimal("0.00")
    return Decimal("0.00"), Decimal("0.00"), tax


def render_pdf(invoice):
    """Render the invoice HTML to a PDF and store it on ``invoice.pdf``."""
    html = render_to_string("billing/invoice_pdf.html", {"invoice": invoice})
    try:
        from xhtml2pdf import pisa
    except ImportError as exc:  # pragma: no cover - depends on environment
        logger.warning("billing: xhtml2pdf unavailable, invoice PDF skipped: %s", exc)
        return None
    from io import BytesIO

    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer)
    if getattr(result, "err", 0):  # pragma: no cover - malformed template
        logger.warning("billing: invoice PDF rendering failed for %s", invoice.number)
        return None
    name = f"{invoice.number.replace('/', '-')}.pdf"
    invoice.pdf.save(name, ContentFile(buffer.getvalue()), save=True)
    return invoice.pdf


@transaction.atomic
def create_invoice(
    company,
    amount,
    *,
    description="",
    provider="",
    provider_ref="",
    gstin=None,
    state_code=None,
    paid=True,
    issued_at=None,
    with_pdf=True,
):
    """Issue a GST invoice for ``company`` and return it."""
    from billing.services import get_subscription

    subscription = get_subscription(company)
    if gstin is None:
        gstin = subscription.gstin
    if state_code is None:
        state_code = subscription.billing_state_code
    amount = _q(amount)
    cgst, sgst, igst = gst_split(amount, state_code)
    issued_at = issued_at or timezone.now()
    invoice = Invoice.objects.create(
        company=company,
        number=next_number(issued_at),
        fy=financial_year(issued_at),
        amount=amount,
        gst_rate=Invoice.GST_RATE,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        total=_q(amount + cgst + sgst + igst),
        gstin=gstin or "",
        place_of_supply=str(state_code or ""),
        description=description or f"{subscription.plan.name} subscription",
        provider=provider or subscription.provider or "",
        provider_ref=provider_ref or "",
        issued_at=issued_at,
        paid_at=issued_at if paid else None,
    )
    if with_pdf:
        try:
            render_pdf(invoice)
        except Exception as exc:  # pragma: no cover - never block a payment
            logger.warning("billing: invoice PDF failed for %s: %s", invoice.number, exc)
    return invoice


def invoice_for_payment(subscription, *, amount=None, provider_ref="", provider=""):
    """Issue the invoice that follows a successful payment webhook."""
    plan = subscription.plan
    if amount is None:
        amount = plan.price_for(subscription.interval)
    if not amount:
        return None
    interval = subscription.get_interval_display().lower()
    return create_invoice(
        subscription.company,
        amount,
        description=f"{plan.name} plan — {interval} subscription",
        provider=provider or subscription.provider,
        provider_ref=provider_ref,
        paid=True,
    )


# --- Monthly bill assembly ----------------------------------------------

SUBSCRIPTION = "SUBSCRIPTION"
SUCCESS_FEE = "SUCCESS_FEE"
AI_OVERAGE = "AI_OVERAGE"


def month_bounds(year, month):
    """``(first_day, first_day_of_next_month)`` for a calendar month."""
    year, month = int(year), int(month)
    last = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1)
    return start, end, date(year, month, last)


def _aware(value):
    """Midnight of ``value`` in the current timezone."""
    stamp = datetime.combine(value, time.min)
    if timezone.is_naive(stamp):
        stamp = timezone.make_aware(stamp)
    return stamp


def _line(kind, label, qty, unit_inr):
    unit = _q(unit_inr)
    total = _q(unit * Decimal(qty))
    return {
        "kind": kind,
        "label": label,
        "qty": int(qty),
        "unit_inr": str(unit),
        "total_inr": str(total),
    }


def _trial_end_date(subscription):
    """The local date the trial ended on, or ``None``."""
    ends_at = getattr(subscription, "trial_ends_at", None)
    if not ends_at:
        return None
    return timezone.localdate(ends_at)


def _subscription_line(subscription, seats, period_start=None, period_last=None):
    """The recurring plan line: per-seat for STARTER, flat for GROWTH/AGENCY.

    Nothing is charged while the subscription is TRIALING — the 14 days are
    free, so a trial company's bill carries only usage and success fees. In the
    month the trial *ends*, the plan is charged from the day after the trial
    end, prorated by days (a grace period delays enforcement, not billing).
    """
    plan = subscription.plan
    if plan is None or plan.code == Plan.FREE:
        return None
    if subscription.status == Subscription.TRIALING:
        return None
    price = Decimal(plan.price_for(Subscription.MONTHLY) or 0)
    if not price:
        return None

    suffix = ""
    if period_start is not None and period_last is not None:
        trial_end = _trial_end_date(subscription)
        if trial_end is not None and period_start <= trial_end <= period_last:
            days_in_month = period_last.day
            billable_days = (period_last - trial_end).days
            if billable_days <= 0:
                return None
            price = _q(price * Decimal(billable_days) / Decimal(days_in_month))
            if not price:
                return None
            suffix = f" — {billable_days}/{days_in_month} days after trial"

    if plan.is_seat_based:
        seats = max(1, int(seats))
        return _line(
            SUBSCRIPTION,
            f"{plan.name} plan — {seats} recruiter seat{'' if seats == 1 else 's'}{suffix}",
            seats,
            price,
        )
    return _line(
        SUBSCRIPTION, f"{plan.name} plan — monthly subscription{suffix}", 1, price
    )


def _success_fee_lines(fees):
    lines = []
    for fee in fees:
        application = getattr(fee, "application", None)
        job = getattr(application, "job", None)
        who = str(getattr(application, "candidate", "") or "hire")
        title = getattr(job, "title", "") or "role"
        lines.append(
            _line(SUCCESS_FEE, f"Success fee — {who} · {title}", 1, fee.amount)
        )
    return lines


def _ai_overage_line(company, plan, period_start_date):
    """AI screens past the plan allowance, priced at ``ai_overage_inr``."""
    from django.db.models import Sum

    if plan is None:
        return None
    allowance = plan.ai_allowance
    unit = Decimal(plan.ai_overage_inr or 0)
    if not unit:
        return None
    total = UsageRecord.objects.filter(
        company=company, kind=UsageRecord.AI_SCREEN, period_start=period_start_date
    ).aggregate(total=Sum("quantity"))["total"]
    over = int(total or 0) - allowance
    if over <= 0:
        return None
    return _line(
        AI_OVERAGE, f"AI screening overage — {over} beyond {allowance} included", over, unit
    )


def monthly_lines(company, year, month):
    """Assemble ``(line_items, placement_fees, charges)`` for one month.

    Pure read: nothing is written, so both :func:`build_monthly_invoice` and
    :func:`projected_bill` can share it.
    """
    from billing import ledger
    from billing.services import get_subscription

    start, end, last = month_bounds(year, month)
    subscription = get_subscription(company)
    plan = subscription.plan
    lines = []
    plan_line = _subscription_line(subscription, subscription.seats_used, start, last)
    if plan_line:
        lines.append(plan_line)

    fees = list(
        PlacementFee.objects.filter(
            company=company,
            created_at__gte=_aware(start),
            created_at__lt=_aware(end),
            invoice__isnull=True,
        )
        .exclude(status=PlacementFee.WAIVED)
        .select_related("application__job", "application__candidate")
        .order_by("created_at", "id")
    )
    lines.extend(_success_fee_lines(fees))

    overage = _ai_overage_line(company, plan, start)
    charges = ledger.charges_for_period(company, _aware(start), _aware(end))
    # usage.consume already books AI overage through the ledger; only fall back
    # to the metered calculation when no such charge exists for the period.
    if overage and not any(c.kind == AI_OVERAGE for c in charges):
        lines.append(overage)
    for charge in charges:
        if charge.kind == AI_OVERAGE and overage:
            # The ledger row stores one lump sum; the invoice should read
            # "2 x Rs 5", so re-use the metered line's qty and unit price.
            lines.append(overage)
            continue
        lines.append(_line(charge.kind, charge.label, 1, charge.amount_inr))
    return lines, fees, charges


def lines_subtotal(lines):
    return _q(sum((Decimal(line["total_inr"]) for line in lines), Decimal("0")))


def build_monthly_invoice(company, year=None, month=None, *, with_pdf=False):
    """Issue (once) the monthly invoice for ``company`` and return it.

    Idempotent: a second call for the same period returns the invoice already
    issued instead of numbering a new one. Returns ``None`` when the period has
    nothing to bill.
    """
    now = timezone.now()
    year = int(year or now.year)
    month = int(month or now.month)
    start, _end, last = month_bounds(year, month)

    existing = Invoice.objects.filter(company=company, period_start=start).first()
    if existing is not None:
        return existing

    lines, fees, charges = monthly_lines(company, year, month)
    if not lines:
        return None
    subtotal = lines_subtotal(lines)
    if subtotal <= 0:
        return None

    from billing.services import get_subscription

    subscription = get_subscription(company)
    cgst, sgst, igst = gst_split(subtotal, subscription.billing_state_code)
    # Dating a mid-month run at the end of the month would issue an invoice in
    # the future; bill the current month "today" and closed months on their
    # last day.
    issued_at = now if (now.year, now.month) == (year, month) else _aware(last)
    with transaction.atomic():
        invoice = Invoice.objects.create(
            company=company,
            number=next_number(issued_at),
            fy=financial_year(issued_at),
            amount=subtotal,
            gst_rate=Invoice.GST_RATE,
            cgst=cgst,
            sgst=sgst,
            igst=igst,
            total=_q(subtotal + cgst + sgst + igst),
            gstin=subscription.gstin or "",
            place_of_supply=subscription.billing_state_code,
            description=f"{start:%B %Y} — {subscription.plan.name} plan and usage",
            line_items=lines,
            period_start=start,
            provider=subscription.provider or "",
            issued_at=issued_at,
        )
        if fees:
            PlacementFee.objects.filter(pk__in=[f.pk for f in fees]).update(
                invoice=invoice, status=PlacementFee.INVOICED
            )
        if charges:
            from billing.models import BillingCharge

            BillingCharge.objects.filter(pk__in=[c.pk for c in charges]).update(
                invoice=invoice
            )
    if with_pdf:
        try:
            render_pdf(invoice)
        except Exception as exc:  # pragma: no cover - never block billing
            logger.warning("billing: invoice PDF failed for %s: %s", invoice.number, exc)
    return invoice


def projected_bill(company, moment=None):
    """What this month's invoice looks like so far — read-only projection."""
    moment = moment or timezone.now()
    start, _end, _last = month_bounds(moment.year, moment.month)
    lines, _fees, _charges = monthly_lines(company, moment.year, moment.month)
    subtotal = lines_subtotal(lines)
    from billing.services import get_subscription

    subscription = get_subscription(company)
    cgst, sgst, igst = gst_split(subtotal, subscription.billing_state_code)
    tax = _q(cgst + sgst + igst)
    return {
        "period_start": start,
        "period_label": f"{start:%B %Y}",
        "lines": lines,
        "subtotal": subtotal,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "tax": tax,
        "total": _q(subtotal + tax),
        "invoiced": Invoice.objects.filter(company=company, period_start=start).exists(),
    }
