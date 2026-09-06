import json

import pytest
from django.urls import reverse

from board.services import network_jobs, network_jobs_for
from board.tests.conftest import make_company, make_job
from careers.models import CareersSite
from jobs.models import Application, CandidateProfile, Job, Skill

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------- listing rules


def test_only_open_published_opted_in_jobs_are_listed(company):
    listed = make_job(company, "Listed role")
    make_job(company, "Draft role", status=Job.DRAFT)
    make_job(company, "Closed role", status=Job.CLOSED)
    make_job(make_company("Unpublished Co", published=False), "Hidden role")
    make_job(make_company("Opted Out Co", list_in_network=False), "Opted out role")
    make_job(  # no careers site at all
        __import__("core.models", fromlist=["Company"]).Company.objects.create(name="No Site Co"),
        "Siteless role",
    )
    assert [j.title for j in network_jobs()] == ["Listed role"]
    assert listed in list(network_jobs())


def test_search_matches_title_skill_and_location(company):
    make_job(company, "Backend Engineer", skills=["Django"], location="Pune, IN")
    make_job(company, "Designer", skills=["Figma"], location="Delhi, IN")
    assert [j.title for j in network_jobs(query="backend")] == ["Backend Engineer"]
    assert [j.title for j in network_jobs(query="figma")] == ["Designer"]
    assert [j.title for j in network_jobs(query="delhi")] == ["Designer"]


def test_remote_filter(company):
    make_job(company, "Remote role", location="Remote")
    make_job(company, "Blank location role", location="")
    make_job(company, "Onsite role", location="Pune, IN")
    assert sorted(j.title for j in network_jobs(remote=True)) == [
        "Blank location role",
        "Remote role",
    ]
    assert [j.title for j in network_jobs(remote=False)] == ["Onsite role"]


def test_skills_filter(company):
    make_job(company, "Py role", skills=["Python"])
    make_job(company, "Go role", skills=["Go"])
    assert [j.title for j in network_jobs(skills=["python"])] == ["Py role"]


# --------------------------------------------------------------------- ranking


def test_network_jobs_for_ranks_by_skill_overlap(company, candidate):
    make_job(company, "Unrelated", skills=["Figma"])
    match = make_job(company, "Python role", skills=["Python"])
    profile = CandidateProfile.objects.create(user=candidate)
    profile.skills.add(Skill.objects.create(company=company, name="python"))
    ranked = network_jobs_for(profile)
    assert ranked[0].pk == match.pk
    assert ranked[0].match == 100
    assert ranked[1].match == 0


def test_network_jobs_for_limits(company, candidate):
    for i in range(3):
        make_job(company, f"Role {i}")
    profile = CandidateProfile.objects.create(user=candidate)
    assert len(network_jobs_for(profile, limit=2)) == 2


# ----------------------------------------------------------------------- pages


def test_list_page_searches_and_paginates(client, company):
    for i in range(25):
        make_job(company, f"Role {i}")
    response = client.get(reverse("board:list"))
    assert response.status_code == 200
    assert len(response.context["jobs"]) == 20
    filtered = client.get(reverse("board:list"), {"q": "Role 7"})
    assert [j.title for j in filtered.context["jobs"]] == ["Role 7"]


def test_detail_404s_for_an_opted_out_job(client, company, job):
    url = reverse("board:job_detail", args=[job.pk])
    assert client.get(url).status_code == 200
    CareersSite.objects.filter(company=company).update(list_in_network=False)
    assert client.get(url).status_code == 404


def test_json_ld_has_required_fields_and_hides_salary(client, company):
    job = make_job(company, "Salaried role", salary_min=100, salary_max=200)
    response = client.get(reverse("board:job_detail", args=[job.pk]))
    data = json.loads(response.context["job_ld"])
    assert data["@type"] == "JobPosting"
    for field in ("title", "description", "datePosted", "hiringOrganization"):
        assert data[field]
    assert data["jobLocation"]["address"]["addressLocality"] == "Pune"
    assert "baseSalary" not in data

    job.show_salary = True
    job.save(update_fields=["show_salary"])
    data = json.loads(client.get(reverse("board:job_detail", args=[job.pk])).context["job_ld"])
    assert data["baseSalary"]["value"]["minValue"] == 100.0


def test_json_ld_uses_telecommute_when_no_location(client, company):
    job = make_job(company, "Anywhere role", location="")
    data = json.loads(client.get(reverse("board:job_detail", args=[job.pk])).context["job_ld"])
    assert data["jobLocationType"] == "TELECOMMUTE"
    assert "jobLocation" not in data


def test_sitemap_and_feed_render(client, job):
    sitemap = client.get(reverse("board:sitemap"))
    assert sitemap.status_code == 200
    assert reverse("board:job_detail", args=[job.pk]) in sitemap.content.decode()
    feed = client.get(reverse("board:feed"))
    assert feed.status_code == 200
    assert job.title in feed.content.decode()


# ----------------------------------------------------------------------- apply


def test_apply_creates_exactly_one_application(client, candidate, job):
    client.force_login(candidate)
    url = reverse("board:job_apply", args=[job.pk])
    assert client.post(url).status_code == 302
    assert client.post(url).status_code == 302
    assert Application.objects.filter(job=job).count() == 1


def test_anonymous_apply_redirects_to_candidate_signup_with_next(client, job):
    response = client.post(reverse("board:job_apply", args=[job.pk]))
    detail = reverse("board:job_detail", args=[job.pk])
    assert response.status_code == 302
    assert response.url == f"{reverse('core:candidate_signup')}?next={detail}"
    assert not Application.objects.exists()


def test_company_member_cannot_apply(client, recruiter, job):
    client.force_login(recruiter)
    response = client.post(reverse("board:job_apply", args=[job.pk]))
    assert response.status_code == 302
    assert not Application.objects.exists()


def test_network_toggle_flips_the_site(client, recruiter, company):
    client.force_login(recruiter)
    response = client.post(reverse("board:network_toggle"))
    assert response.status_code == 302
    assert CareersSite.objects.get(company=company).list_in_network is False
