from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from clients.models import ClientAccess, Submission

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cooldown():
    cache.clear()
    yield
    cache.clear()


def test_portal_renders_without_login(client, access, submission):
    response = client.get(reverse("clients:portal", args=[access.token]))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Initech" in body  # client branding
    assert "Acme Staffing" in body  # providing firm
    assert "Django Developer" in body  # grouped by job
    assert "Senior Django engineer" in body
    assert "82%" in body  # AI fit score
    assert "Strong match on Django" in body
    # standalone chrome: no recruiter sidebar
    assert "ip-shell" not in body


def test_portal_touches_last_used(client, access):
    assert access.last_used_at is None
    client.get(reverse("clients:portal", args=[access.token]))
    access.refresh_from_db()
    assert access.last_used_at is not None


def test_portal_groups_submissions_by_job(client, access, client_row, company, make_job, make_application):
    from clients.models import Submission as S

    job2 = make_job(company, title="React Developer", client=client_row)
    app2 = make_application(job2)
    S.objects.create(application=app2, client=client_row)
    response = client.get(reverse("clients:portal", args=[access.token]))
    titles = [group["job"].title for group in response.context["groups"]]
    assert titles == sorted(titles)
    assert "React Developer" in titles


def test_expired_token_shows_contact_page(client, access):
    access.expires_at = timezone.now() - timedelta(days=1)
    access.save()
    response = client.get(reverse("clients:portal", args=[access.token]))
    assert response.status_code == 404
    assert b"no longer valid" in response.content
    assert b"Acme Staffing" in response.content


def test_revoked_token_is_404(client, revoked_access):
    response = client.get(reverse("clients:portal", args=[revoked_access.token]))
    assert response.status_code == 404


def test_unknown_token_is_404(client):
    response = client.get(reverse("clients:portal", args=["not-a-real-token"]))
    assert response.status_code == 404


def test_resume_streams_through_token_url(client, access, client_row, job, make_application):
    application = make_application(job, resume=True)
    submission = Submission.objects.create(application=application, client=client_row)
    url = reverse("clients:portal_resume", args=[access.token, submission.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert b"fake resume" in b"".join(response.streaming_content)
    assert "attachment" in response["Content-Disposition"]
    # the media path is never handed to the client
    assert application.candidate.resume.name not in response["Content-Disposition"]


def test_resume_requires_valid_token(client, revoked_access, client_row, job, make_application):
    application = make_application(job, resume=True)
    submission = Submission.objects.create(application=application, client=client_row)
    response = client.get(
        reverse("clients:portal_resume", args=[revoked_access.token, submission.pk])
    )
    assert response.status_code == 404


def test_resume_of_another_clients_submission_is_404(
    client, access, other_company, make_job, make_application
):
    from clients.models import Client as ClientRow

    foreign_client = ClientRow.objects.create(company=other_company, name="Foreign Co")
    foreign_job = make_job(other_company, title="Foreign Job", client=foreign_client)
    foreign_app = make_application(foreign_job, resume=True)
    foreign_sub = Submission.objects.create(application=foreign_app, client=foreign_client)
    response = client.get(
        reverse("clients:portal_resume", args=[access.token, foreign_sub.pk])
    )
    assert response.status_code == 404


def test_missing_resume_is_404(client, access, submission):
    response = client.get(
        reverse("clients:portal_resume", args=[access.token, submission.pk])
    )
    assert response.status_code == 404


def test_feedback_updates_submission_and_notifies_recruiter(
    client, access, submission, mailoutbox
):
    url = reverse("clients:portal_feedback", args=[access.token, submission.pk])
    response = client.post(
        url, {"decision": Submission.SHORTLISTED, "comment": "Nice profile", "rating": "4"}
    )
    assert response.status_code == 302
    submission.refresh_from_db()
    assert submission.status == Submission.SHORTLISTED
    assert submission.client_feedback == "Nice profile"
    assert submission.client_rating == 4
    assert submission.decided_at is not None
    assert any(submission.submitted_by.email in m.to for m in mailoutbox)


def test_feedback_rate_limited_per_token(client, access, submission, application, client_row, job, make_application):
    other = Submission.objects.create(
        application=make_application(job), client=client_row
    )
    first = client.post(
        reverse("clients:portal_feedback", args=[access.token, submission.pk]),
        {"decision": Submission.REJECTED, "comment": "", "rating": ""},
    )
    assert first.status_code == 302
    second = client.post(
        reverse("clients:portal_feedback", args=[access.token, other.pk]),
        {"decision": Submission.REJECTED, "comment": "", "rating": ""},
    )
    assert second.status_code == 302
    other.refresh_from_db()
    assert other.status == Submission.SUBMITTED  # blocked by the cooldown


def test_feedback_rejects_invalid_decision(client, access, submission):
    response = client.post(
        reverse("clients:portal_feedback", args=[access.token, submission.pk]),
        {"decision": "HIRED", "comment": "", "rating": ""},
    )
    assert response.status_code == 302
    submission.refresh_from_db()
    assert submission.status == Submission.SUBMITTED


def test_feedback_needs_valid_token(client, revoked_access, submission):
    response = client.post(
        reverse("clients:portal_feedback", args=[revoked_access.token, submission.pk]),
        {"decision": Submission.REJECTED},
    )
    assert response.status_code == 404
    submission.refresh_from_db()
    assert submission.status == Submission.SUBMITTED


def test_feedback_get_not_allowed(client, access, submission):
    response = client.get(
        reverse("clients:portal_feedback", args=[access.token, submission.pk])
    )
    assert response.status_code == 405


def test_portal_empty_state(client, client_row):
    access = ClientAccess.objects.create(client=client_row, email="new@initech.test")
    response = client.get(reverse("clients:portal", args=[access.token]))
    assert response.status_code == 200
    assert b"No candidates yet" in response.content


def test_submission_notifies_client_contacts(client_row, application, access, mailoutbox):
    from clients.services import submit_application

    submit_application(application, client_row, note="see attached")
    assert any(access.email in m.to for m in mailoutbox)
