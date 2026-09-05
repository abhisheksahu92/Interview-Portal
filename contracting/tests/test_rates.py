"""Rate arithmetic: every unit, plus the proration rule for monthly retainers."""

from datetime import date
from decimal import Decimal

import pytest

from contracting import rates
from contracting.models import Engagement

pytestmark = pytest.mark.django_db


def test_hour_rate_multiplies_total_hours(engagement, make_timesheet):
    timesheet = make_timesheet(engagement, days=5, hours=8)  # 40 hours
    assert timesheet.total_hours == Decimal("40.00")
    assert rates.bill_amount(timesheet) == Decimal("80000.00")
    assert rates.pay_amount(timesheet) == Decimal("60000.00")


def test_hour_rate_handles_fractional_hours(engagement, make_timesheet):
    timesheet = make_timesheet(engagement, days=3, hours=7.5)  # 22.5 hours
    assert rates.bill_amount(timesheet) == Decimal("45000.00")


def test_day_rate_counts_days_with_any_hours(contractor, client_row, make_engagement, make_timesheet):
    engagement = make_engagement(
        contractor,
        client_row,
        rate_unit=Engagement.DAY,
        bill_rate_inr=Decimal("6000"),
        pay_rate_inr=Decimal("4500"),
    )
    timesheet = make_timesheet(engagement, days=4, hours=6)
    assert timesheet.days_worked == 4
    assert rates.bill_amount(timesheet) == Decimal("24000.00")
    assert rates.pay_amount(timesheet) == Decimal("18000.00")


def test_day_rate_ignores_zero_hour_days(contractor, client_row, make_engagement, make_timesheet):
    engagement = make_engagement(contractor, client_row, rate_unit=Engagement.DAY, bill_rate_inr=1000)
    timesheet = make_timesheet(engagement, days=5, hours=8)
    timesheet.entries = timesheet.entries[:2] + [
        {"date": "2026-04-09", "hours": 0, "note": "leave"}
    ]
    timesheet.save()
    assert timesheet.days_worked == 2
    assert rates.bill_amount(timesheet) == Decimal("2000.00")


def test_month_rate_prorates_over_working_days(contractor, client_row, make_engagement, make_timesheet):
    """A full month of working days bills the whole retainer."""
    engagement = make_engagement(
        contractor, client_row, rate_unit=Engagement.MONTH, bill_rate_inr=Decimal("220000")
    )
    # April 2026: 22 Mon–Fri days, all of them worked.
    timesheet = make_timesheet(
        engagement,
        start=date(2026, 4, 1),
        days=0,
        period_end=date(2026, 4, 30),
    )
    timesheet.entries = [
        {"date": d.isoformat(), "hours": 8, "note": ""}
        for d in _weekdays(date(2026, 4, 1), date(2026, 4, 30))
    ]
    timesheet.save()
    assert rates.month_divisor(timesheet) == Decimal("22")
    assert rates.bill_amount(timesheet) == Decimal("220000.00")


def test_month_rate_half_a_month_bills_half(contractor, client_row, make_engagement, make_timesheet):
    engagement = make_engagement(
        contractor, client_row, rate_unit=Engagement.MONTH, bill_rate_inr=Decimal("220000")
    )
    timesheet = make_timesheet(engagement, start=date(2026, 4, 1), days=0, period_end=date(2026, 4, 30))
    worked = _weekdays(date(2026, 4, 1), date(2026, 4, 30))[:11]
    timesheet.entries = [{"date": d.isoformat(), "hours": 8, "note": ""} for d in worked]
    timesheet.save()
    assert rates.bill_amount(timesheet) == Decimal("110000.00")


def test_month_unit_rate_is_a_per_day_figure(contractor, client_row, make_engagement, make_timesheet):
    engagement = make_engagement(
        contractor, client_row, rate_unit=Engagement.MONTH, bill_rate_inr=Decimal("220000")
    )
    timesheet = make_timesheet(engagement, start=date(2026, 4, 1), days=0, period_end=date(2026, 4, 30))
    assert rates.unit_rate_for(timesheet, engagement.bill_rate_inr) == Decimal("10000.00")


def test_working_days_excludes_weekends():
    assert rates.working_days(date(2026, 4, 6), date(2026, 4, 12)) == 5
    assert rates.working_days(date(2026, 4, 11), date(2026, 4, 12)) == 0


def test_tds_defaults_to_ten_percent(engagement):
    assert engagement.tds_percent == Decimal("10.00")
    assert rates.tds_for(engagement, Decimal("60000")) == Decimal("6000.00")


def test_tds_percent_is_configurable(contractor, client_row, make_engagement):
    engagement = make_engagement(contractor, client_row, tds_percent=Decimal("2"))
    assert rates.tds_for(engagement, Decimal("50000")) == Decimal("1000.00")


def test_amounts_round_half_up_to_paise(contractor, client_row, make_engagement, make_timesheet):
    engagement = make_engagement(contractor, client_row, bill_rate_inr=Decimal("333.335"))
    timesheet = make_timesheet(engagement, days=1, hours=1)
    assert rates.bill_amount(timesheet) == Decimal("333.34")


def _weekdays(start, end):
    from datetime import timedelta

    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days
