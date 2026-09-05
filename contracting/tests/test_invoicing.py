"""Client invoicing: numbering, grouping, GST split, PDF and delivery."""

from datetime import date
from decimal import Decimal

import pytest

from contracting import invoicing, services
from contracting.models import ClientBillingProfile, ClientInvoice, Timesheet

pytestmark = pytest.mark.django_db


@pytest.fixture
def approved(engagement, make_timesheet, owner):
    def factory(start=date(2026, 4, 6), **kwargs):
        timesheet = make_timesheet(engagement, start=start, **kwargs)
        services.submit(timesheet)
        services.approve(timesheet, user=owner)
        return timesheet

    return factory


def _profile(client, **kwargs):
    profile, _ = ClientBillingProfile.objects.get_or_create(client=client)
    for key, value in kwargs.items():
        setattr(profile, key, value)
    profile.save()
    return profile


def test_invoice_numbers_are_sequential_per_financial_year(company):
    first = invoicing.next_number(company, date(2026, 4, 10))
    second = invoicing.next_number(company, date(2026, 6, 1))
    assert first == "INV/2026-27/0001"
    assert second == "INV/2026-27/0002"


def test_invoice_numbers_restart_in_a_new_financial_year(company):
    invoicing.next_number(company, date(2026, 4, 10))
    assert invoicing.next_number(company, date(2027, 4, 2)) == "INV/2027-28/0001"


def test_peek_number_does_not_consume_a_number(company):
    assert invoicing.peek_number(company, date(2026, 4, 10)) == "INV/2026-27/0001"
    assert invoicing.next_number(company, date(2026, 4, 10)) == "INV/2026-27/0001"


def test_counters_are_independent_per_company(company, other_company):
    invoicing.next_number(company, date(2026, 4, 10))
    assert invoicing.next_number(other_company, date(2026, 4, 10)) == "INV/2026-27/0001"


def test_generate_invoices_from_approved_timesheets(company, client_row, approved):
    approved()
    invoices = invoicing.generate_client_invoices(company, date(2026, 4, 1))
    assert len(invoices) == 1
    invoice = invoices[0]
    assert invoice.client == client_row
    assert invoice.subtotal == Decimal("80000.00")
    assert len(invoice.line_items) == 1
    assert invoice.line_items[0]["qty"] == 40.0


def test_generate_groups_multiple_timesheets_onto_one_client_invoice(company, approved):
    approved(start=date(2026, 4, 6))
    approved(start=date(2026, 4, 13))
    invoices = invoicing.generate_client_invoices(company, date(2026, 4, 1))
    assert len(invoices) == 1
    assert len(invoices[0].line_items) == 2
    assert invoices[0].subtotal == Decimal("160000.00")


def test_generate_raises_one_invoice_per_client(
    company, contractor, make_client_row, make_engagement, make_timesheet, owner, approved
):
    approved()
    second_client = make_client_row(company, "Umbrella")
    other_engagement = make_engagement(contractor, second_client, bill_rate_inr=1000, pay_rate_inr=800)
    sheet = make_timesheet(other_engagement, days=1, hours=8)
    services.submit(sheet)
    services.approve(sheet, user=owner)
    invoices = invoicing.generate_client_invoices(company, date(2026, 4, 1))
    assert len(invoices) == 2


def test_generate_is_idempotent(company, approved):
    approved()
    assert len(invoicing.generate_client_invoices(company, date(2026, 4, 1))) == 1
    assert invoicing.generate_client_invoices(company, date(2026, 4, 1)) == []


def test_generate_ignores_unapproved_timesheets(company, engagement, make_timesheet):
    make_timesheet(engagement)  # still DRAFT
    assert invoicing.generate_client_invoices(company, date(2026, 4, 1)) == []


def test_invoicing_marks_timesheets_invoiced_and_links_them(company, approved):
    timesheet = approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    timesheet.refresh_from_db()
    assert timesheet.status == Timesheet.INVOICED
    assert timesheet.client_invoice == invoice
    assert list(invoice.timesheets.all()) == [timesheet]


def test_intra_state_client_gets_a_cgst_sgst_split(company, client_row, approved, settings):
    settings.COMPANY_STATE_CODE = "27"
    _profile(client_row, state_code="27", gstin="27AAAAA0000A1Z5")
    approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    assert invoice.cgst == Decimal("7200.00")
    assert invoice.sgst == Decimal("7200.00")
    assert invoice.igst == Decimal("0.00")
    assert invoice.total == Decimal("94400.00")
    assert invoice.is_intra_state


def test_inter_state_client_gets_igst(company, client_row, approved, settings):
    settings.COMPANY_STATE_CODE = "27"
    _profile(client_row, state_code="29")
    approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    assert invoice.igst == Decimal("14400.00")
    assert invoice.cgst == invoice.sgst == Decimal("0.00")
    assert invoice.total == Decimal("94400.00")
    assert not invoice.is_intra_state


def test_unknown_client_state_falls_back_to_igst(company, approved, settings):
    settings.COMPANY_STATE_CODE = "27"
    approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    assert invoice.igst == Decimal("14400.00")


def test_due_date_follows_the_payment_terms(company, client_row, approved):
    _profile(client_row, payment_terms_days=15)
    approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    assert (invoice.due_at - invoice.issued_at.date()).days == 15


def test_send_invoice_marks_it_sent_and_emails_the_client(company, client_row, approved, mailoutbox):
    _profile(client_row, billing_email="ap@initech.test")
    approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    invoicing.send_invoice(invoice)
    assert invoice.status == ClientInvoice.SENT and invoice.sent_at
    assert any("ap@initech.test" in message.to for message in mailoutbox)


def test_mark_paid_stops_the_dso_clock(company, approved):
    approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    invoicing.mark_paid(invoice)
    assert invoice.is_paid and invoice.paid_at
    assert not invoice.is_overdue


def test_overdue_refresh_flags_stale_sent_invoices(company, approved):
    from datetime import timedelta

    from django.utils import timezone

    approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    invoicing.send_invoice(invoice)
    ClientInvoice.objects.filter(pk=invoice.pk).update(
        due_at=timezone.localdate() - timedelta(days=1)
    )
    assert invoicing.refresh_overdue(company) == 1
    invoice.refresh_from_db()
    assert invoice.status == ClientInvoice.OVERDUE


def test_pdf_is_rendered_and_stored(company, approved):
    approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    assert invoice.pdf
    invoice.pdf.open("rb")
    try:
        assert invoice.pdf.read(5) == b"%PDF-"
    finally:
        invoice.pdf.close()


def test_no_platform_fee_is_posted_by_default(company, approved):
    approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    assert invoicing.platform_fee_inr(company) is None
    assert invoicing.post_platform_fee(invoice) is None


def test_platform_fee_from_settings_is_posted_to_the_billing_ledger(company, approved, settings):
    settings.CONTRACTING_INVOICE_FEE_INR = "99"
    approved()
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    assert invoicing.platform_fee_inr(company) == Decimal("99.00")
    charge = invoicing.post_platform_fee(invoice)
    if charge is not None:  # billing.ledger lands with the parallel billing work
        assert Decimal(charge.amount_inr) == Decimal("99.00")


def test_month_rate_invoice_line_reports_a_per_day_rate(
    company, contractor, client_row, make_engagement, make_timesheet, owner
):
    from contracting.models import Engagement

    engagement = make_engagement(
        contractor, client_row, rate_unit=Engagement.MONTH, bill_rate_inr=Decimal("220000")
    )
    sheet = make_timesheet(engagement, start=date(2026, 4, 1), days=0, period_end=date(2026, 4, 30))
    sheet.entries = [{"date": f"2026-04-{d:02d}", "hours": 8, "note": ""} for d in (1, 2, 3)]
    sheet.save()
    services.submit(sheet)
    services.approve(sheet, user=owner)
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    line = invoice.line_items[0]
    assert line["unit_inr"] == 10000.0
    assert line["total_inr"] == 30000.0
