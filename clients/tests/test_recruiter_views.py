import pytest
from django.urls import reverse

from clients.models import Client, ClientAccess, Submission
from clients.tests.conftest import enable_client_portal

pytestmark = pytest.mark.django_db


def test_index_lists_only_own_company_clients(client, owner, client_row, make_client_row, other_company):
    make_client_row(other_company, "Globex Client")
    client.force_login(owner)
    response = client.get(reverse("clients:index"))
    assert response.status_code == 200
    assert b"Initech" in response.content
    assert b"Globex Client" not in response.content


def test_create_client(client, owner, company):
    client.force_login(owner)
    response = client.post(
        reverse("clients:create"),
        {"name": "Umbrella Corp", "contact_name": "Ada", "contact_email": "ada@u.test", "notes": ""},
        follow=True,
    )
    assert response.status_code == 200
    created = Client.objects.get(name="Umbrella Corp")
    assert created.company == company


def test_edit_client(client, owner, client_row):
    client.force_login(owner)
    response = client.post(
        reverse("clients:edit", args=[client_row.pk]),
        {"name": "Initech Ltd", "contact_name": "", "contact_email": "", "notes": "VIP"},
    )
    assert response.status_code == 302
    client_row.refresh_from_db()
    assert client_row.name == "Initech Ltd" and client_row.notes == "VIP"


def test_detail_of_other_company_client_is_404(client, other_owner, client_row):
    client.force_login(other_owner)
    response = client.get(reverse("clients:detail", args=[client_row.pk]))
    assert response.status_code == 404


def test_detail_shows_jobs_and_submissions(client, owner, client_row, submission):
    client.force_login(owner)
    response = client.get(reverse("clients:detail", args=[client_row.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Django Developer" in body
    assert "Submitted" in body


def test_feature_gate_blocks_recruiter_views(client, owner, company):
    enable_client_portal(company, enabled=False)
    client.force_login(owner)
    assert client.get(reverse("clients:index")).status_code == 403


def test_interviewer_role_cannot_manage_clients(client, interviewer):
    client.force_login(interviewer)
    assert client.get(reverse("clients:index")).status_code == 403


def test_anonymous_recruiter_view_redirects_to_login(client):
    response = client.get(reverse("clients:index"))
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_submit_application_creates_submission(client, owner, application, client_row):
    client.force_login(owner)
    response = client.post(
        reverse("clients:submit_application", args=[application.pk]),
        {"client": client_row.pk, "note": "Interviewed L1", "notify_client": "on"},
    )
    assert response.status_code == 302
    submission = Submission.objects.get(application=application, client=client_row)
    assert submission.submitted_by == owner
    assert submission.note == "Interviewed L1"
    assert submission.status == Submission.SUBMITTED


def test_submit_form_defaults_to_job_client(client, owner, application, client_row):
    client.force_login(owner)
    response = client.get(reverse("clients:submit_application", args=[application.pk]))
    assert response.context["form"].fields["client"].initial == client_row.pk


def test_cross_company_submission_rejected_by_form(
    client, owner, application, other_company, make_client_row
):
    foreign = make_client_row(other_company, "Foreign Co")
    client.force_login(owner)
    response = client.post(
        reverse("clients:submit_application", args=[application.pk]),
        {"client": foreign.pk, "note": ""},
    )
    assert response.status_code == 200
    assert not Submission.objects.filter(client=foreign).exists()


def test_cross_company_submission_rejected_by_service(
    application, other_company, make_client_row
):
    from clients.services import CrossCompanySubmission, submit_application

    foreign = make_client_row(other_company, "Foreign Co")
    with pytest.raises(CrossCompanySubmission):
        submit_application(application, foreign)


def test_submitting_other_companys_application_is_404(
    client, other_owner, application, other_company, make_client_row
):
    make_client_row(other_company, "Foreign Co")
    client.force_login(other_owner)
    response = client.get(reverse("clients:submit_application", args=[application.pk]))
    assert response.status_code == 404


def test_submission_detail_timeline(client, owner, submission):
    submission.record_client_decision(Submission.INTERVIEW_REQUESTED, "Set up a call", 5)
    client.force_login(owner)
    response = client.get(reverse("clients:submission_detail", args=[submission.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Interview requested" in body and "Set up a call" in body


def test_access_create_emails_link(client, owner, client_row, mailoutbox):
    client.force_login(owner)
    response = client.post(
        reverse("clients:access_create", args=[client_row.pk]),
        {"email": "cto@initech.test", "valid_days": 10},
    )
    assert response.status_code == 302
    access = ClientAccess.objects.get(email="cto@initech.test")
    assert access.is_active and access.expires_at is not None
    assert len(mailoutbox) == 1
    assert access.token in mailoutbox[0].body


def test_access_revoke_and_resend(client, owner, client_row, access, mailoutbox):
    client.force_login(owner)
    client.post(reverse("clients:access_revoke", args=[client_row.pk, access.pk]))
    access.refresh_from_db()
    assert access.revoked

    old_token = access.token
    client.post(reverse("clients:access_resend", args=[client_row.pk, access.pk]))
    access.refresh_from_db()
    assert access.token != old_token and access.is_active
    assert any(access.token in m.body for m in mailoutbox)


def test_access_of_other_company_is_404(client, other_owner, client_row, access, other_company, make_client_row):
    foreign = make_client_row(other_company, "Foreign Co")
    client.force_login(other_owner)
    response = client.post(
        reverse("clients:access_revoke", args=[foreign.pk, access.pk])
    )
    assert response.status_code == 404


def test_job_client_view_sets_and_clears_client(client, owner, company, make_job, client_row):
    job = make_job(company, title="QA Engineer")
    client.force_login(owner)
    response = client.post(reverse("clients:job_client", args=[job.pk]), {"client": client_row.pk})
    assert response.status_code == 302
    job.refresh_from_db()
    assert job.client == client_row

    client.post(reverse("clients:job_client", args=[job.pk]), {"client": ""})
    job.refresh_from_db()
    assert job.client is None


def test_job_client_form_rejects_foreign_client(company, other_company, make_job, make_client_row):
    from clients.forms import JobClientForm

    job = make_job(company)
    foreign = make_client_row(other_company, "Foreign Co")
    form = JobClientForm({"client": foreign.pk}, company=company, job=job)
    assert not form.is_valid()


def test_detail_renders_the_shared_access_links_table(client, owner, client_row, access):
    """The portal-links table is core/_access_links_table.html, same as the
    team-invitations table on the members page."""
    access.touch()
    client.force_login(owner)
    response = client.get(reverse("clients:detail", args=[client_row.pk]))
    body = response.content.decode()
    assert "ip-access-links" in body
    assert access.email in body
    assert "Portal access" in body  # link_purpose column
    assert "Active" in body  # status badge
    assert "Last used" in body
    assert reverse("clients:access_revoke", args=[client_row.pk, access.pk]) in body
    assert reverse("clients:access_resend", args=[client_row.pk, access.pk]) in body
    assert "confirm(" in body  # revoke asks first


def test_detail_marks_a_revoked_link_and_drops_its_revoke_button(
    client, owner, client_row, access
):
    access.revoke()
    client.force_login(owner)
    body = client.get(reverse("clients:detail", args=[client_row.pk])).content.decode()
    assert "Revoked" in body
    assert reverse("clients:access_revoke", args=[client_row.pk, access.pk]) not in body
    assert reverse("clients:access_resend", args=[client_row.pk, access.pk]) in body
