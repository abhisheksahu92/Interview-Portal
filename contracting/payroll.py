"""Monthly contractor payroll: gross from pay rates, TDS, net, and a CSV.

Gross uses the same :mod:`contracting.rates` arithmetic as client billing, so a
contractor is never paid on a different reading of a timesheet than the client
is billed on. TDS is withheld per engagement (``Engagement.tds_percent``,
default 10% for 194J/194C) and summed, rather than applying one blended rate to
a contractor working two engagements at different sections.

The CSV columns are the ones greytHR and Keka expect from an "employee payout"
import: ``employee_id, name, pan, days, gross, tds, net, bank_account, ifsc``.
"""

import csv
import io
import logging
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction

from contracting import rates
from contracting.models import PayrollRun, Timesheet, money

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "employee_id",
    "name",
    "pan",
    "days",
    "gross",
    "tds",
    "net",
    "bank_account",
    "ifsc",
]

#: Timesheets a payroll run pays on — approved work, invoiced or not.
PAYABLE_STATES = (Timesheet.APPROVED, Timesheet.INVOICED)


def payable_timesheets(company, period_start, period_end):
    return (
        Timesheet.objects.for_company(company)
        .filter(
            status__in=PAYABLE_STATES,
            period_end__gte=period_start,
            period_end__lte=period_end,
        )
        .select_related("engagement__contractor")
        .order_by("engagement__contractor__name", "period_start")
    )


def build_rows(company, period_start, period_end):
    """One payout row per contractor with any payable work in the window."""
    buckets = {}
    for timesheet in payable_timesheets(company, period_start, period_end):
        engagement = timesheet.engagement
        contractor = engagement.contractor
        gross = rates.pay_amount(timesheet)
        row = buckets.setdefault(
            contractor.pk,
            {
                "contractor_id": contractor.pk,
                "employee_id": contractor.payroll_id,
                "name": contractor.name,
                "pan": contractor.pan or "",
                "days": 0,
                "hours": Decimal("0"),
                "gross": Decimal("0"),
                "tds": Decimal("0"),
                "net": Decimal("0"),
                "bank_account": contractor.bank_account,
                "ifsc": contractor.ifsc,
            },
        )
        row["days"] += timesheet.days_worked
        row["hours"] += Decimal(timesheet.total_hours or 0)
        row["gross"] += gross
        row["tds"] += rates.tds_for(engagement, gross)

    rows = []
    for row in buckets.values():
        row["gross"] = money(row["gross"])
        row["tds"] = money(row["tds"])
        row["net"] = money(row["gross"] - row["tds"])
        row["hours"] = str(money(row["hours"]))
        for key in ("gross", "tds", "net"):
            row[key] = str(row[key])
        rows.append(row)
    rows.sort(key=lambda r: r["name"].lower())
    return rows


def csv_bytes(rows):
    """The payroll rows as an HRMS-importable CSV."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})
    return buffer.getvalue().encode("utf-8")


def csv_filename(run):
    return f"payroll-{run.month:%Y-%m}.csv"


@transaction.atomic
def run_payroll(company, month, *, created_by=None):
    """Compute (or recompute) ``company``'s payroll for ``month``.

    ``month`` is any date inside the payroll month. Re-running replaces the
    stored rows and CSV for that month — a draft run is a calculation, not a
    payment, so it stays idempotent per month.
    """
    from contracting import services

    period_start = services.month_start(month)
    _, period_end = services.month_bounds(period_start)
    rows = build_rows(company, period_start, period_end)
    totals = {
        key: money(sum(Decimal(row[key]) for row in rows)) if rows else money(0)
        for key in ("gross", "tds", "net")
    }
    run, _ = PayrollRun.objects.get_or_create(
        company=company, month=period_start, defaults={"created_by": created_by}
    )
    if run.status == PayrollRun.FINAL:
        return run
    run.rows = rows
    run.gross_total = totals["gross"]
    run.tds_total = totals["tds"]
    run.net_total = totals["net"]
    if run.csv:
        run.csv.delete(save=False)
    run.save(
        update_fields=["rows", "gross_total", "tds_total", "net_total", "csv"]
    )
    run.csv.save(csv_filename(run), ContentFile(csv_bytes(rows)), save=True)
    return run


def finalise(run):
    """Lock a run so a later recompute cannot silently change what was paid."""
    run.status = PayrollRun.FINAL
    run.save(update_fields=["status"])
    return run
