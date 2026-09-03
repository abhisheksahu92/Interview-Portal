import pytest
from django.urls import reverse

from jobs.models import Job


def test_landing_renders_for_anonymous(client):
    response = client.get(reverse("web:home"))
    assert response.status_code == 200
    assert b"Create a company" in response.content or b"create a company" in response.content
    assert reverse("core:candidate_signup").encode() in response.content


@pytest.mark.django_db
def test_landing_redirects_member_to_dashboard(client, recruiter):
    client.force_login(recruiter)
    response = client.get(reverse("web:home"))
    assert response.status_code == 302
    assert response.url == reverse("web:dashboard")


@pytest.mark.django_db
def test_landing_redirects_interviewer_to_queue(client, interviewer):
    client.force_login(interviewer)
    response = client.get(reverse("web:home"))
    assert response.status_code == 302
    assert response.url == reverse("web:interviewer_queue")


@pytest.mark.django_db
def test_landing_redirects_candidate_to_portal(client, candidate):
    client.force_login(candidate)
    response = client.get(reverse("web:home"))
    assert response.status_code == 302
    assert response.url == reverse("web:candidate_home")


@pytest.mark.django_db
def test_job_browse_lists_only_open_jobs(client, company, make_job):
    make_job(company, title="Open Role", status=Job.OPEN)
    make_job(company, title="Draft Role", status=Job.DRAFT)
    response = client.get(reverse("web:job_browse"))
    assert response.status_code == 200
    assert b"Open Role" in response.content
    assert b"Draft Role" not in response.content
