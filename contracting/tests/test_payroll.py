"""Payroll: gross from pay rates, per-engagement TDS, net, and the HRMS CSV."""

import csv
import io
from datetime import date
from decimal import Decimal

import pytest

from contracting import payroll, services
from contracting.models import PayrollRun

pytestmark = pytest.mark.django_db


@pytest.fixture
def approve(owner):
    def factory(timesheet):
        services.submit(timesheet)
        services.approve(timesheet, user=owner)
        return timesheet

    return factory


def test_gross_tds_and_net_for_one_contractor(company, engagement, make_timesheet, approve):
    approve(make_timesheet(engagement))  # 40 h x 1500 = 60000 gross
    run = payroll.run_payroll(company, date(2026, 4, 15))
    row = run.rows[0]
    assert row["gross"] == "60000.00"
    assert row["tds"] == "6000.00"
    assert row["net"] == "54000.00"
    assert row["days"] == 5


def test_totals_are_stored_on_the_run(company, engagement, make_timesheet, approve):
    approve(make_timesheet(engagement))
    run = payroll.run_payroll(company, date(2026, 4, 15))
    assert run.gross_total == Decimal("60000.00")
    assert run.tds_total == Decimal("6000.00")
    assert run.net_total == Decimal("54000.00")
    assert run.headcount == 1


def test_tds_is_applied_per_engagement_not_blended(
    company, contractor, make_client_row, make_engagement, make_timesheet, approve
):
    """Two engagements at 10% and 2% withhold their own rates."""
    first = make_engagement(
        contractor, make_client_row(company, "A"), pay_rate_inr=Decimal("1000")
    )
    second = make_engagement(
        contractor,
        make_client_row(company, "B"),
        pay_rate_inr=Decimal("1000"),
        tds_percent=Decimal("2"),
    )
    approve(make_timesheet(first, start=date(2026, 4, 6), days=1, hours=10))
    approve(make_timesheet(second, start=date(2026, 4, 13), days=1, hours=10))
    run = payroll.run_payroll(company, date(2026, 4, 1))
    row = run.rows[0]
    assert row["gross"] == "20000.00"
    assert row["tds"] == "1200.00"  # 1000 + 200, not 20000 x 6%
    assert row["net"] == "18800.00"


def test_unapproved_work_is_not_paid(company, engagement, make_timesheet):
    make_timesheet(engagement)  # DRAFT
    run = payroll.run_payroll(company, date(2026, 4, 1))
    assert run.rows == [] and run.gross_total == Decimal("0.00")


def test_invoiced_timesheets_are_still_paid(company, engagement, make_timesheet, approve):
    from contracting.invoicing import generate_client_invoices

    approve(make_timesheet(engagement))
    generate_client_invoices(company, date(2026, 4, 1))
    run = payroll.run_payroll(company, date(2026, 4, 1))
    assert run.rows[0]["gross"] == "60000.00"


def test_only_the_requested_month_is_paid(company, engagement, make_timesheet, approve):
    approve(make_timesheet(engagement, start=date(2026, 4, 6)))
    approve(make_timesheet(engagement, start=date(2026, 5, 4)))
    april = payroll.run_payroll(company, date(2026, 4, 20))
    assert april.gross_total == Decimal("60000.00")


def test_running_twice_recomputes_the_same_month(company, engagement, make_timesheet, approve):
    approve(make_timesheet(engagement, start=date(2026, 4, 6)))
    first = payroll.run_payroll(company, date(2026, 4, 1))
    approve(make_timesheet(engagement, start=date(2026, 4, 13)))
    second = payroll.run_payroll(company, date(2026, 4, 1))
    assert first.pk == second.pk
    assert second.gross_total == Decimal("120000.00")
    assert PayrollRun.objects.filter(company=company).count() == 1


def test_a_finalised_run_is_not_recomputed(company, engagement, make_timesheet, approve):
    approve(make_timesheet(engagement, start=date(2026, 4, 6)))
    payroll.finalise(payroll.run_payroll(company, date(2026, 4, 1)))
    approve(make_timesheet(engagement, start=date(2026, 4, 13)))
    again = payroll.run_payroll(company, date(2026, 4, 1))
    assert again.gross_total == Decimal("60000.00")


def test_csv_has_the_hrms_columns(company, engagement, make_timesheet, approve):
    approve(make_timesheet(engagement))
    run = payroll.run_payroll(company, date(2026, 4, 1))
    reader = csv.DictReader(io.StringIO(payroll.csv_bytes(run.rows).decode()))
    assert reader.fieldnames == [
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
    row = next(reader)
    assert row["name"] == "Ravi Kumar"
    assert row["pan"] == "ABCDE1234F"
    assert row["bank_account"] == "12345678901"
    assert row["ifsc"] == "HDFC0000123"
    assert row["net"] == "54000.00"


def test_csv_file_is_attached_to_the_run(company, engagement, make_timesheet, approve):
    approve(make_timesheet(engagement))
    run = payroll.run_payroll(company, date(2026, 4, 1))
    assert run.csv
    run.csv.open("rb")
    try:
        assert b"employee_id" in run.csv.read()
    finally:
        run.csv.close()


def test_payroll_is_scoped_to_one_tenant(
    company, other_company, other_owner, make_contractor, make_client_row, make_engagement,
    make_timesheet, engagement, approve,
):
    approve(make_timesheet(engagement))
    foreign_contractor = make_contractor(other_company, "Someone Else")
    foreign = make_engagement(foreign_contractor, make_client_row(other_company, "Foreign"))
    foreign_sheet = make_timesheet(foreign)
    services.submit(foreign_sheet)
    services.approve(foreign_sheet, user=other_owner)

    run = payroll.run_payroll(company, date(2026, 4, 1))
    assert [row["name"] for row in run.rows] == ["Ravi Kumar"]


def test_employee_id_falls_back_to_a_generated_payroll_id(company, make_contractor):
    contractor = make_contractor(company, employee_id="")
    assert contractor.payroll_id == f"C{contractor.pk:05d}"


def test_bill_month_command_invoices_every_entitled_tenant(
    company, engagement, make_timesheet, approve
):
    from io import StringIO

    from django.core.management import call_command

    approve(make_timesheet(engagement, start=date(2026, 4, 6)))
    out = StringIO()
    call_command("bill_contracting_month", "--month", "2026-04", stdout=out)
    assert company.client_invoices.count() == 1
    assert "1 invoice(s) raised" in out.getvalue()


def test_bill_month_command_skips_companies_without_the_feature(
    company, engagement, make_timesheet, approve
):
    from django.core.management import call_command

    from contracting.tests.conftest import enable_contracting

    approve(make_timesheet(engagement, start=date(2026, 4, 6)))
    enable_contracting(company, enabled=False)
    call_command("bill_contracting_month", "--month", "2026-04")
    assert company.client_invoices.count() == 0
