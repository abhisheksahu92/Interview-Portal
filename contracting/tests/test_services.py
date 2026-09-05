"""Onboarding, engagement creation and the timesheet state machine."""

from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from contracting import services
from contracting.models import Contractor, Engagement, OnboardingDocument, Timesheet

pytestmark = pytest.mark.django_db


def _pdf(name="pan.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 scan", content_type="application/pdf")


def test_bank_details_round_trip_through_the_encrypted_field(company, make_contractor):
    contractor = make_contractor(company, bank={"account_number": "999", "ifsc": "SBIN0001"})
    contractor.refresh_from_db()
    assert contractor.bank == {"account_number": "999", "ifsc": "SBIN0001"}
    assert contractor.bank_account == "999"


def test_bank_details_are_ciphertext_in_the_database(company, make_contractor):
    contractor = make_contractor(company, bank={"account_number": "SECRET-ACCT"})
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT bank FROM contracting_contractor WHERE id = %s", [contractor.pk]
        )
        raw = cursor.fetchone()[0]
    assert "SECRET-ACCT" not in raw
    assert raw.startswith("gAAAAA")


def test_onboarding_checklist_tracks_fields_and_documents(company, make_contractor):
    contractor = make_contractor(company, pan="", bank={})
    progress = services.onboarding_progress(contractor)
    assert progress["done"] == 0 and not progress["complete"]
    assert "PAN number" in progress["missing"]

    contractor.pan = "ABCDE1234F"
    contractor.bank = {"account_number": "1"}
    contractor.save()
    for kind in OnboardingDocument.REQUIRED_KINDS:
        services.add_document(contractor, kind, _pdf(f"{kind.lower()}.pdf"))
    assert services.is_onboarding_complete(contractor)


def test_completing_the_checklist_activates_an_onboarding_contractor(company, make_contractor):
    contractor = make_contractor(company, status=Contractor.ONBOARDING)
    for kind in OnboardingDocument.REQUIRED_KINDS:
        services.add_document(contractor, kind, _pdf(f"{kind.lower()}.pdf"))
    contractor.refresh_from_db()
    assert contractor.status == Contractor.ACTIVE


def test_create_engagement_seeds_a_billing_profile(contractor, client_row):
    engagement = services.create_engagement(
        contractor,
        client_row,
        role_title="SRE",
        start=date(2026, 4, 1),
        bill_rate_inr=Decimal("100"),
        pay_rate_inr=Decimal("80"),
    )
    assert engagement.client == client_row
    assert client_row.billing_profile.billing_email == client_row.contact_email


def test_create_engagement_refuses_a_client_from_another_tenant(
    contractor, other_company, make_client_row
):
    foreign = make_client_row(other_company, "Globex Client")
    with pytest.raises(ValueError):
        services.create_engagement(
            contractor,
            foreign,
            role_title="SRE",
            start=date(2026, 4, 1),
            bill_rate_inr=1,
            pay_rate_inr=1,
        )


def test_total_hours_is_recomputed_from_the_entries(engagement, make_timesheet):
    timesheet = make_timesheet(engagement, days=2, hours=4)
    timesheet.total_hours = Decimal("999")
    timesheet.save()
    timesheet.refresh_from_db()
    assert timesheet.total_hours == Decimal("8.00")


def test_negative_hours_are_clamped_to_zero(engagement, make_timesheet):
    timesheet = make_timesheet(engagement, days=1, hours=8)
    timesheet.entries = [{"date": "2026-04-06", "hours": -5, "note": ""}]
    timesheet.save()
    assert timesheet.total_hours == Decimal("0.00")


def test_state_machine_draft_to_submitted_to_approved(engagement, make_timesheet, owner):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    assert timesheet.status == Timesheet.SUBMITTED and timesheet.submitted_at
    services.approve(timesheet, user=owner, note="ok")
    assert timesheet.status == Timesheet.APPROVED
    assert timesheet.approved_by_user == owner and timesheet.approved_at


def test_state_machine_rejects_then_allows_resubmission(engagement, make_timesheet, owner):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    services.reject(timesheet, user=owner, note="Friday is wrong")
    assert timesheet.status == Timesheet.REJECTED
    assert timesheet.client_note == "Friday is wrong"
    services.submit(timesheet)
    assert timesheet.status == Timesheet.SUBMITTED
    assert timesheet.client_note == ""


def test_state_machine_forbids_approving_a_draft(engagement, make_timesheet, owner):
    timesheet = make_timesheet(engagement)
    with pytest.raises(services.InvalidTransition):
        services.approve(timesheet, user=owner)


def test_state_machine_forbids_submitting_an_approved_sheet(engagement, make_timesheet, owner):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    services.approve(timesheet, user=owner)
    with pytest.raises(services.InvalidTransition):
        services.submit(timesheet)


def test_an_invoiced_timesheet_is_frozen(engagement, make_timesheet, owner, client_row):
    from contracting.invoicing import generate_client_invoices

    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    services.approve(timesheet, user=owner)
    generate_client_invoices(engagement.contractor.company, date(2026, 4, 1))
    timesheet.refresh_from_db()
    assert timesheet.status == Timesheet.INVOICED
    with pytest.raises(services.InvalidTransition):
        services.reject(timesheet, user=owner)


def test_draft_cannot_be_saved_once_submitted(engagement, make_timesheet):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    with pytest.raises(services.InvalidTransition):
        services.save_draft(timesheet, [])


def test_submitting_notifies_the_client(engagement, make_timesheet, access, mailoutbox):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    assert any(access.email in message.to for message in mailoutbox)


def test_week_bounds_run_monday_to_sunday():
    start, end = services.week_bounds(date(2026, 4, 9))  # a Thursday
    assert start == date(2026, 4, 6) and end == date(2026, 4, 12)


def test_month_bounds_cover_the_whole_month():
    start, end = services.month_bounds(date(2026, 2, 17))
    assert start == date(2026, 2, 1) and end == date(2026, 2, 28)


def test_engagement_margin_per_unit(engagement):
    assert engagement.margin_per_unit == Decimal("500.00")
    assert engagement.margin_percent == Decimal("25.00")


def test_timesheet_periods_are_unique_per_engagement(engagement, make_timesheet):
    from django.db import IntegrityError

    make_timesheet(engagement, start=date(2026, 5, 4))
    with pytest.raises(IntegrityError):
        make_timesheet(engagement, start=date(2026, 5, 4))


def test_get_or_create_timesheet_is_idempotent(engagement):
    first = services.get_or_create_timesheet(engagement, date(2026, 6, 1))
    second = services.get_or_create_timesheet(engagement, date(2026, 6, 1))
    assert first.pk == second.pk


def test_engagement_status_display_choices():
    assert dict(Engagement.RATE_UNIT_CHOICES)[Engagement.MONTH] == "Per month"
