"""Rate arithmetic: turning an approved timesheet into an amount of money.

One module so the client-billing side and the payroll side can never disagree
about what "a day" or "a month" means:

===========  ===================================================================
``HOUR``     ``rate × total_hours``
``DAY``      ``rate × days worked`` (a day with any hours on it counts as one)
``MONTH``    ``rate × days worked ÷ working days in the period`` — a monthly
             retainer prorated over the Mon–Fri days of the timesheet period, so
             a full month bills the full rate and half a month bills half.
===========  ===================================================================

Amounts are computed at full ``Decimal`` precision and rounded once, at the
end, half-up. The per-unit rate reported alongside a prorated month is a
*display* figure derived from the same numbers; ``total_inr`` is authoritative.
"""

from datetime import timedelta
from decimal import Decimal

from contracting.models import Engagement, money


def working_days(start, end):
    """Mon–Fri days in the inclusive range ``start``..``end``."""
    if end < start:
        return 0
    count = 0
    day = start
    while day <= end:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def calendar_days(start, end):
    if end < start:
        return 0
    return (end - start).days + 1


def quantity(timesheet, rate_unit=None):
    """The billable quantity of a timesheet in its rate unit."""
    unit = rate_unit or timesheet.engagement.rate_unit
    if unit == Engagement.HOUR:
        return Decimal(timesheet.total_hours or 0)
    return Decimal(timesheet.days_worked)


def month_divisor(timesheet):
    """Days a full monthly rate is spread over for this period."""
    divisor = working_days(timesheet.period_start, timesheet.period_end)
    if divisor:
        return Decimal(divisor)
    days = calendar_days(timesheet.period_start, timesheet.period_end)
    return Decimal(days) if days else Decimal("0")


def amount_for(timesheet, rate, rate_unit=None):
    """Money owed for ``timesheet`` at ``rate`` in the engagement's rate unit."""
    unit = rate_unit or timesheet.engagement.rate_unit
    rate = Decimal(rate or 0)
    qty = quantity(timesheet, unit)
    if unit == Engagement.MONTH:
        divisor = month_divisor(timesheet)
        if not divisor:
            return money(0)
        return money(rate * qty / divisor)
    return money(rate * qty)


def unit_rate_for(timesheet, rate, rate_unit=None):
    """The per-quantity rate to show on an invoice line.

    For HOUR/DAY that is the engagement rate itself; for a prorated MONTH it is
    the rate divided by the period's working days, i.e. a per-day figure.
    """
    unit = rate_unit or timesheet.engagement.rate_unit
    rate = Decimal(rate or 0)
    if unit != Engagement.MONTH:
        return money(rate)
    divisor = month_divisor(timesheet)
    return money(rate / divisor) if divisor else money(0)


def unit_label(rate_unit):
    return {
        Engagement.HOUR: "hours",
        Engagement.DAY: "days",
        Engagement.MONTH: "days",
    }.get(rate_unit, "units")


def bill_amount(timesheet):
    """What the client owes for this timesheet."""
    return amount_for(timesheet, timesheet.engagement.bill_rate_inr)


def pay_amount(timesheet):
    """What the contractor earns for this timesheet, before TDS."""
    return amount_for(timesheet, timesheet.engagement.pay_rate_inr)


def tds_for(engagement, gross):
    """TDS withheld from ``gross`` at the engagement's configured percentage."""
    percent = Decimal(
        engagement.tds_percent
        if engagement.tds_percent is not None
        else Engagement.DEFAULT_TDS_PERCENT
    )
    return money(Decimal(gross or 0) * percent / Decimal(100))
