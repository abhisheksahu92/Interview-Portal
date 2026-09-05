"""Read-time contracting metrics: margin, DSO, utilisation.

:func:`summary` is the public seam — the analytics app imports it lazily so it
keeps working on installs where the ``contracting`` feature is off. Everything
is computed on read from the rows the app already stores; nothing is cached.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from contracting import rates
from contracting.models import ClientInvoice, Engagement, Timesheet, money

#: Days of invoice history the DSO figure looks back over.
DSO_WINDOW_DAYS = 180


def engagement_margins(company, since=None):
    """Bill, pay and margin per engagement, richest margin first.

    Only approved (or already invoiced) work counts — a draft timesheet is a
    claim, not revenue.
    """
    timesheets = (
        Timesheet.objects.for_company(company)
        .filter(status__in=(Timesheet.APPROVED, Timesheet.INVOICED))
        .select_related("engagement__contractor", "engagement__client")
    )
    if since is not None:
        timesheets = timesheets.filter(period_end__gte=since)
    buckets = {}
    for timesheet in timesheets:
        engagement = timesheet.engagement
        row = buckets.setdefault(
            engagement.pk,
            {
                "engagement": engagement,
                "contractor": engagement.contractor.name,
                "client": engagement.client.name,
                "role_title": engagement.role_title,
                "rate_unit": engagement.get_rate_unit_display(),
                "quantity": Decimal("0"),
                "unit_label": rates.unit_label(engagement.rate_unit),
                "bill": Decimal("0"),
                "pay": Decimal("0"),
            },
        )
        row["quantity"] += rates.quantity(timesheet)
        row["bill"] += rates.bill_amount(timesheet)
        row["pay"] += rates.pay_amount(timesheet)
    rows = []
    for row in buckets.values():
        row["bill"] = money(row["bill"])
        row["pay"] = money(row["pay"])
        row["margin"] = money(row["bill"] - row["pay"])
        row["margin_percent"] = (
            money(row["margin"] * 100 / row["bill"]) if row["bill"] else Decimal("0.00")
        )
        rows.append(row)
    rows.sort(key=lambda r: r["margin"], reverse=True)
    return rows


def dso(company, window_days=DSO_WINDOW_DAYS):
    """Days sales outstanding: mean age of invoices raised in the window.

    A paid invoice contributes issue→payment days; an unpaid one contributes
    issue→today, so a stack of ageing invoices pushes the figure up rather than
    being quietly excluded. ``None`` when nothing has been invoiced.
    """
    since = timezone.now() - timedelta(days=window_days)
    invoices = ClientInvoice.objects.for_company(company).filter(issued_at__gte=since)
    ages = [invoice.days_outstanding for invoice in invoices]
    if not ages:
        return None
    return round(sum(ages) / len(ages), 1)


def receivables(company):
    """Outstanding client money: ``{"open", "overdue", "count"}`` in rupees."""
    unpaid = ClientInvoice.objects.for_company(company).exclude(
        status=ClientInvoice.PAID
    )
    today = timezone.localdate()
    open_total = Decimal("0")
    overdue_total = Decimal("0")
    count = 0
    for invoice in unpaid:
        count += 1
        open_total += money(invoice.total)
        if invoice.due_at and invoice.due_at < today:
            overdue_total += money(invoice.total)
    return {"open": money(open_total), "overdue": money(overdue_total), "count": count}


def utilisation(company, days=30):
    """Share of open engagements that logged approved work in the last ``days``.

    A crude but honest bench measure: an active placement with no approved
    timesheet in a month is either unbilled or idle, and both need looking at.
    """
    open_engagements = [
        engagement
        for engagement in Engagement.objects.filter(
            contractor__company=company, status=Engagement.ACTIVE
        ).select_related("contractor")
    ]
    if not open_engagements:
        return {"engaged": 0, "total": 0, "percent": 0}
    since = timezone.localdate() - timedelta(days=days)
    engaged_ids = set(
        Timesheet.objects.for_company(company)
        .filter(
            status__in=(Timesheet.APPROVED, Timesheet.INVOICED), period_end__gte=since
        )
        .values_list("engagement_id", flat=True)
    )
    engaged = sum(1 for e in open_engagements if e.pk in engaged_ids)
    total = len(open_engagements)
    return {
        "engaged": engaged,
        "total": total,
        "percent": int(round(engaged * 100 / total)),
    }


def summary(company):
    """Headline contracting numbers for a company — the analytics seam.

    Safe to call for any tenant: a company with no contracting data gets zeroes
    and ``None`` for DSO rather than an exception.
    """
    margins = engagement_margins(company)
    bill = money(sum((row["bill"] for row in margins), Decimal("0")))
    pay = money(sum((row["pay"] for row in margins), Decimal("0")))
    margin = money(bill - pay)
    return {
        "active_contractors": Engagement.objects.filter(
            contractor__company=company, status=Engagement.ACTIVE
        )
        .values("contractor_id")
        .distinct()
        .count(),
        "open_engagements": Engagement.objects.filter(
            contractor__company=company, status=Engagement.ACTIVE
        ).count(),
        "pending_timesheets": Timesheet.objects.for_company(company)
        .awaiting_approval()
        .count(),
        "billed": bill,
        "paid_out": pay,
        "margin": margin,
        "margin_percent": money(margin * 100 / bill) if bill else Decimal("0.00"),
        "dso_days": dso(company),
        "receivables": receivables(company),
        "utilisation": utilisation(company),
        "engagements": margins,
    }
