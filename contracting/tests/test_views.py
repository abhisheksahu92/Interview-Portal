"""Recruiter workspace: feature gating, tenant isolation and the money screens."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from contracting import invoicing, services
from contracting.models import ClientBillingProfile, Contractor, Engagement, Timesheet
from contracting.tests.conftest import enable_contracting

pytestmark = pytest.mark.django_db


def test_dashboard_renders_margin(client, owner, company, engagement, make_timesheet):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    services.approve(timesheet, user=owner)
    client.force_login(owner)
    response = client.get(reverse("contracting:index"))
    assert response.status_code == 200
    assert b"Gross margin" in response.content


def test_feature_gate_blocks_every_recruiter_screen(client, owner, company):
    enable_contracting(company, enabled=False)
    client.force_login(owner)
    for name in ("index", "contractor_list", "engagement_list", "timesheet_queue",
                 "invoice_list", "payroll_list"):
        assert client.get(reverse(f"contracting:{name}")).status_code == 403


def test_interviewers_are_not_allowed_in(client, interviewer):
    client.force_login(interviewer)
    assert client.get(reverse("contracting:contractor_list")).status_code == 403


def test_anonymous_visitors_are_redirected_to_login(client):
    response = client.get(reverse("contracting:contractor_list"))
    assert response.status_code in (302, 403)


def test_contractor_list_shows_only_this_tenant(client, owner, contractor, other_company, make_contractor):
    make_contractor(other_company, "Foreign Person")
    client.force_login(owner)
    response = client.get(reverse("contracting:contractor_list"))
    body = response.content.decode()
    assert "Ravi Kumar" in body and "Foreign Person" not in body


def test_another_tenants_contractor_is_404(client, other_owner, contractor):
    client.force_login(other_owner)
    assert client.get(
        reverse("contracting:contractor_detail", args=[contractor.pk])
    ).status_code == 404


def test_create_contractor_stores_encrypted_bank_details(client, owner, company):
    client.force_login(owner)
    response = client.post(
        reverse("contracting:contractor_create"),
        {
            "name": "Meera Iyer",
            "email": "meera@example.test",
            "phone": "",
            "pan": "abcde9999z",
            "uan": "",
            "employee_id": "",
            "status": Contractor.ONBOARDING,
            "notes": "",
            "bank_holder": "Meera Iyer",
            "bank_account_number": "5555",
            "bank_ifsc": "ICIC0001",
            "bank_name": "ICICI",
        },
    )
    assert response.status_code == 302
    created = Contractor.objects.get(name="Meera Iyer")
    assert created.company == company
    assert created.pan == "ABCDE9999Z"
    assert created.bank["account_number"] == "5555"


def test_document_upload_rejects_a_disguised_file(client, owner, contractor):
    client.force_login(owner)
    bad = SimpleUploadedFile("pan.pdf", b"MZ not a pdf", content_type="application/pdf")
    client.post(
        reverse("contracting:document_upload", args=[contractor.pk]),
        {"kind": "PAN", "file": bad, "note": ""},
    )
    assert contractor.documents.count() == 0


def test_document_upload_accepts_a_real_pdf(client, owner, contractor):
    client.force_login(owner)
    good = SimpleUploadedFile("pan.pdf", b"%PDF-1.4 ok", content_type="application/pdf")
    client.post(
        reverse("contracting:document_upload", args=[contractor.pk]),
        {"kind": "PAN", "file": good, "note": ""},
    )
    assert contractor.documents.count() == 1


def test_rotating_the_link_invalidates_the_old_token(client, owner, contractor):
    old = contractor.token
    client.force_login(owner)
    client.post(reverse("contracting:contractor_rotate_link", args=[contractor.pk]))
    contractor.refresh_from_db()
    assert contractor.token != old
    assert client.get(reverse("contracting:contractor_portal", args=[old])).status_code == 404


def test_engagement_create_view(client, owner, contractor, client_row):
    client.force_login(owner)
    response = client.post(
        reverse("contracting:engagement_create", args=[contractor.pk]),
        {
            "client": client_row.pk,
            "job": "",
            "role_title": "Data Engineer",
            "start": "2026-04-01",
            "end": "",
            "bill_rate_inr": "2500",
            "pay_rate_inr": "1800",
            "rate_unit": Engagement.HOUR,
            "tds_percent": "10",
            "po_number": "PO-9",
            "status": Engagement.ACTIVE,
        },
    )
    assert response.status_code == 302
    assert Engagement.objects.filter(contractor=contractor, role_title="Data Engineer").exists()


def test_engagement_form_refuses_another_tenants_client(client, owner, contractor, other_company, make_client_row):
    foreign = make_client_row(other_company, "Foreign Client")
    client.force_login(owner)
    response = client.post(
        reverse("contracting:engagement_create", args=[contractor.pk]),
        {
            "client": foreign.pk,
            "role_title": "X",
            "start": "2026-04-01",
            "bill_rate_inr": "10",
            "pay_rate_inr": "5",
            "rate_unit": Engagement.HOUR,
            "tds_percent": "10",
            "status": Engagement.ACTIVE,
        },
    )
    assert response.status_code == 200
    assert not Engagement.objects.filter(client=foreign).exists()


def test_engagement_form_rejects_a_pay_rate_above_the_bill_rate(client, owner, contractor, client_row):
    client.force_login(owner)
    response = client.post(
        reverse("contracting:engagement_create", args=[contractor.pk]),
        {
            "client": client_row.pk,
            "role_title": "X",
            "start": "2026-04-01",
            "bill_rate_inr": "100",
            "pay_rate_inr": "200",
            "rate_unit": Engagement.HOUR,
            "tds_percent": "10",
            "status": Engagement.ACTIVE,
        },
    )
    assert response.status_code == 200
    assert b"cannot exceed the bill rate" in response.content


def test_recruiter_can_approve_from_the_queue(client, owner, engagement, make_timesheet):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    client.force_login(owner)
    client.post(reverse("contracting:timesheet_decide", args=[timesheet.pk, "approve"]))
    timesheet.refresh_from_db()
    assert timesheet.status == Timesheet.APPROVED and timesheet.approved_by_user == owner


def test_queue_hides_another_tenants_timesheets(
    client, other_owner, engagement, make_timesheet
):
    make_timesheet(engagement)
    client.force_login(other_owner)
    response = client.get(reverse("contracting:timesheet_queue") + "?status=")
    assert b"Ravi Kumar" not in response.content


def test_invoice_generate_and_send_flow(client, owner, company, engagement, make_timesheet, mailoutbox):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    services.approve(timesheet, user=owner)
    client.force_login(owner)
    client.post(reverse("contracting:invoice_generate"), {"month": "2026-04-01"})
    invoice = company.client_invoices.get()
    assert invoice.subtotal > 0

    client.post(reverse("contracting:invoice_send", args=[invoice.pk]))
    invoice.refresh_from_db()
    assert invoice.status == "SENT"

    client.post(reverse("contracting:invoice_mark_paid", args=[invoice.pk]))
    invoice.refresh_from_db()
    assert invoice.is_paid


def test_invoice_pdf_downloads(client, owner, company, engagement, make_timesheet):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    services.approve(timesheet, user=owner)
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    client.force_login(owner)
    response = client.get(reverse("contracting:invoice_pdf", args=[invoice.pk]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


def test_another_tenant_cannot_read_an_invoice(client, other_owner, company, engagement, make_timesheet, owner):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    services.approve(timesheet, user=owner)
    invoice = invoicing.generate_client_invoices(company, date(2026, 4, 1))[0]
    client.force_login(other_owner)
    assert client.get(reverse("contracting:invoice_detail", args=[invoice.pk])).status_code == 404


def test_billing_profile_can_be_edited(client, owner, client_row):
    client.force_login(owner)
    response = client.post(
        reverse("contracting:billing_profile", args=[client_row.pk]),
        {
            "gstin": "27aaaaa0000a1z5",
            "state_code": "27",
            "billing_email": "ap@initech.test",
            "billing_address": "Pune",
            "payment_terms_days": "45",
        },
    )
    assert response.status_code == 302
    profile = ClientBillingProfile.objects.get(client=client_row)
    assert profile.gstin == "27AAAAA0000A1Z5" and profile.payment_terms_days == 45


def test_billing_profile_rejects_a_bad_state_code(client, owner, client_row):
    client.force_login(owner)
    response = client.post(
        reverse("contracting:billing_profile", args=[client_row.pk]),
        {"state_code": "MH", "payment_terms_days": "30"},
    )
    assert response.status_code == 200
    assert b"two-digit GST state code" in response.content


def test_payroll_run_and_csv_download(client, owner, company, engagement, make_timesheet):
    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    services.approve(timesheet, user=owner)
    client.force_login(owner)
    response = client.post(reverse("contracting:payroll_run"), {"month": "2026-04-01"}, follow=True)
    assert response.status_code == 200
    run = company.payroll_runs.get()
    csv_response = client.get(reverse("contracting:payroll_download", args=[run.pk]))
    assert csv_response["Content-Type"] == "text/csv"
    assert b"Ravi Kumar" in csv_response.content
