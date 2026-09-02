import pytest
from django.urls import reverse

from jobs.models import Job, Skill


@pytest.mark.django_db
def test_manage_list_requires_login(client):
    response = client.get(reverse("jobs:manage_job_list"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_interviewer_cannot_manage_jobs(client, interviewer):
    client.force_login(interviewer)
    assert client.get(reverse("jobs:manage_job_list")).status_code == 403
    assert client.get(reverse("jobs:manage_job_create")).status_code == 403
    assert client.get(reverse("jobs:skill_list")).status_code == 403


@pytest.mark.django_db
def test_candidate_without_company_cannot_manage(client, candidate):
    client.force_login(candidate.user)
    assert client.get(reverse("jobs:manage_job_list")).status_code == 403


@pytest.mark.django_db
def test_manage_list_is_company_scoped(client, recruiter, job, other_company):
    Job.objects.create(company=other_company, title="Foreign Job", status=Job.OPEN)
    client.force_login(recruiter)
    content = client.get(reverse("jobs:manage_job_list")).content
    assert b"Django Dev" in content
    assert b"Foreign Job" not in content


@pytest.mark.django_db
def test_cannot_open_other_company_job(client, other_recruiter, job):
    client.force_login(other_recruiter)
    assert client.get(reverse("jobs:manage_job_detail", args=[job.pk])).status_code == 404
    assert client.get(reverse("jobs:manage_job_edit", args=[job.pk])).status_code == 404


@pytest.mark.django_db
def test_cannot_edit_other_company_stage(client, other_recruiter, job):
    stage = job.stages.first()
    client.force_login(other_recruiter)
    url = reverse("jobs:stage_edit", args=[job.pk, stage.pk])
    assert client.post(url, {"name": "Hacked", "order": 1, "kind": "HR"}).status_code == 404
    stage.refresh_from_db()
    assert stage.name == "Screening"


@pytest.mark.django_db
def test_cannot_delete_other_company_skill(client, other_recruiter, company):
    skill = Skill.objects.create(company=company, name="Python")
    client.force_login(other_recruiter)
    response = client.post(reverse("jobs:skill_delete", args=[skill.pk]))
    assert response.status_code == 404
    assert Skill.objects.filter(pk=skill.pk).exists()


@pytest.mark.django_db
def test_job_form_only_offers_own_company_skills(client, recruiter, company, other_company):
    Skill.objects.create(company=company, name="Mine")
    Skill.objects.create(company=other_company, name="Theirs")
    client.force_login(recruiter)
    content = client.get(reverse("jobs:manage_job_create")).content
    assert b"Mine" in content
    assert b"Theirs" not in content
