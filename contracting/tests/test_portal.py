"""Token surfaces: the contractor's timesheet link and the client portal panel."""

from datetime import date

import pytest
from django.urls import reverse

from clients.models import ClientAccess
from contracting import services
from contracting.models import Timesheet
from contracting.tests.conftest import enable_contracting

pytestmark = pytest.mark.django_db


# --- contractor self-service ------------------------------------------------ #


def test_contractor_page_lists_their_engagements(client, contractor, engagement):
    response = client.get(reverse("contracting:contractor_portal", args=[contractor.token]))
    assert response.status_code == 200
    assert b"Django Developer" in response.content


def test_opening_the_page_stamps_last_used(client, contractor, engagement):
    client.get(reverse("contracting:contractor_portal", args=[contractor.token]))
    contractor.refresh_from_db()
    assert contractor.last_used_at is not None


def test_an_unknown_token_is_404(client):
    assert client.get(reverse("contracting:contractor_portal", args=["nope"])).status_code == 404


def test_a_revoked_token_is_gone(client, contractor):
    contractor.revoke()
    response = client.get(reverse("contracting:contractor_portal", args=[contractor.token]))
    assert response.status_code == 410


def test_an_expired_token_is_gone(client, contractor):
    from datetime import timedelta

    from django.utils import timezone

    contractor.expires_at = timezone.now() - timedelta(days=1)
    contractor.save(update_fields=["expires_at"])
    response = client.get(reverse("contracting:contractor_portal", args=[contractor.token]))
    assert response.status_code == 410


def test_one_contractor_cannot_open_anothers_timesheet(client, company, make_contractor, timesheet):
    intruder = make_contractor(company, "Intruder", email="x@example.test")
    url = reverse("contracting:contractor_timesheet", args=[intruder.token, timesheet.pk])
    assert client.get(url).status_code == 404


def test_saving_a_draft_keeps_it_editable(client, contractor, timesheet):
    url = reverse("contracting:contractor_timesheet", args=[contractor.token, timesheet.pk])
    response = client.post(url, {"action": "save", "hours-2026-04-06": "6.5"}, follow=True)
    assert response.status_code == 200
    timesheet.refresh_from_db()
    assert timesheet.status == Timesheet.DRAFT
    assert str(timesheet.total_hours) == "6.50"


def test_submitting_moves_the_timesheet_out_of_draft(client, contractor, timesheet):
    url = reverse("contracting:contractor_timesheet", args=[contractor.token, timesheet.pk])
    client.post(url, {"action": "submit", "hours-2026-04-06": "8"}, follow=True)
    timesheet.refresh_from_db()
    assert timesheet.status == Timesheet.SUBMITTED


def test_hours_outside_the_period_are_ignored(client, contractor, timesheet):
    url = reverse("contracting:contractor_timesheet", args=[contractor.token, timesheet.pk])
    client.post(url, {"action": "save", "hours-2025-01-01": "40", "hours-2026-04-06": "2"})
    timesheet.refresh_from_db()
    assert str(timesheet.total_hours) == "2.00"
    assert [entry["date"] for entry in timesheet.entries] == ["2026-04-06"]


def test_more_than_24_hours_in_a_day_is_refused(client, contractor, timesheet):
    url = reverse("contracting:contractor_timesheet", args=[contractor.token, timesheet.pk])
    client.post(url, {"action": "save", "hours-2026-04-06": "30"})
    timesheet.refresh_from_db()
    assert str(timesheet.total_hours) == "40.00"  # unchanged fixture grid


def test_a_submitted_timesheet_cannot_be_edited_through_the_link(client, contractor, timesheet):
    services.submit(timesheet)
    url = reverse("contracting:contractor_timesheet", args=[contractor.token, timesheet.pk])
    client.post(url, {"action": "save", "hours-2026-04-06": "1"})
    timesheet.refresh_from_db()
    assert str(timesheet.total_hours) == "40.00"


# --- client portal panel ---------------------------------------------------- #


def test_portal_shows_the_timesheets_section(client, access, timesheet):
    services.submit(timesheet)
    response = client.get(reverse("clients:portal", args=[access.token]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Timesheets" in body and "Ravi Kumar" in body


def test_portal_hides_timesheets_without_the_feature(client, access, company, timesheet):
    services.submit(timesheet)
    enable_contracting(company, enabled=False)
    response = client.get(reverse("clients:portal", args=[access.token]))
    assert b"contracting-timesheets" not in response.content


def test_client_can_approve_from_the_portal(client, access, timesheet):
    services.submit(timesheet)
    response = client.post(
        reverse("contracting:portal_timesheet_decide", args=[access.token, timesheet.pk, "approve"]),
        {"note": "looks right"},
    )
    assert response.status_code == 200
    timesheet.refresh_from_db()
    assert timesheet.status == Timesheet.APPROVED
    assert timesheet.approved_by_access == access
    assert timesheet.client_note == "looks right"


def test_client_can_reject_with_a_note(client, access, timesheet):
    services.submit(timesheet)
    client.post(
        reverse("contracting:portal_timesheet_decide", args=[access.token, timesheet.pk, "reject"]),
        {"note": "Friday was a holiday"},
    )
    timesheet.refresh_from_db()
    assert timesheet.status == Timesheet.REJECTED
    assert timesheet.client_note == "Friday was a holiday"


def test_approval_response_is_the_panel_partial(client, access, timesheet):
    services.submit(timesheet)
    response = client.post(
        reverse("contracting:portal_timesheet_decide", args=[access.token, timesheet.pk, "approve"]),
        {"note": ""},
    )
    assert b'id="contracting-timesheets"' in response.content


def test_a_client_cannot_approve_another_clients_timesheet(
    client, company, make_client_row, timesheet
):
    services.submit(timesheet)
    other = make_client_row(company, "Umbrella")
    other_access = ClientAccess.objects.create(client=other, email="ap@umbrella.test")
    response = client.post(
        reverse(
            "contracting:portal_timesheet_decide",
            args=[other_access.token, timesheet.pk, "approve"],
        )
    )
    assert response.status_code == 404
    timesheet.refresh_from_db()
    assert timesheet.status == Timesheet.SUBMITTED


def test_a_revoked_portal_link_cannot_approve(client, access, timesheet):
    services.submit(timesheet)
    access.revoke()
    response = client.post(
        reverse("contracting:portal_timesheet_decide", args=[access.token, timesheet.pk, "approve"])
    )
    assert response.status_code == 404
    timesheet.refresh_from_db()
    assert timesheet.status == Timesheet.SUBMITTED


def test_approving_twice_is_refused_by_the_state_machine(client, access, timesheet):
    services.submit(timesheet)
    url = reverse("contracting:portal_timesheet_decide", args=[access.token, timesheet.pk, "approve"])
    client.post(url)
    timesheet.refresh_from_db()
    approved_at = timesheet.approved_at
    client.post(url)
    timesheet.refresh_from_db()
    assert timesheet.approved_at == approved_at


def test_get_is_not_allowed_on_the_decision_endpoint(client, access, timesheet):
    response = client.get(
        reverse("contracting:portal_timesheet_decide", args=[access.token, timesheet.pk, "approve"])
    )
    assert response.status_code == 405


def test_metrics_summary_is_safe_for_an_empty_company(other_company):
    from contracting import metrics

    summary = metrics.summary(other_company)
    assert summary["margin"] == 0 and summary["dso_days"] is None


def test_metrics_summary_reports_margin_and_dso(company, engagement, make_timesheet, owner):
    from contracting import invoicing, metrics

    timesheet = make_timesheet(engagement)
    services.submit(timesheet)
    services.approve(timesheet, user=owner)
    invoicing.generate_client_invoices(company, date(2026, 4, 1))
    summary = metrics.summary(company)
    assert summary["billed"] == 80000
    assert summary["margin"] == 20000
    assert summary["dso_days"] is not None
    # Utilisation looks at the recent past, so widen the window to reach April.
    assert metrics.utilisation(company, days=100000)["percent"] == 100
    assert summary["utilisation"]["total"] == 1
