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
def test_job_browse_lists_only_open_jobs(client, listed_company, make_job):
    make_job(listed_company, title="Open Role", status=Job.OPEN)
    make_job(listed_company, title="Draft Role", status=Job.DRAFT)
    response = client.get(reverse("web:job_browse"))
    assert response.status_code == 200
    assert b"Open Role" in response.content
    assert b"Draft Role" not in response.content


@pytest.mark.django_db
def test_job_browse_hides_companies_that_did_not_opt_in(client, company, make_job):
    """An open requisition is not consent to publish - the careers site is."""
    make_job(company, title="Private Role", status=Job.OPEN)

    response = client.get(reverse("web:job_browse"))

    assert b"Private Role" not in response.content
