import pytest
from django.urls import reverse

from jobs.models import Application, Job, PipelineStage, Skill


@pytest.mark.django_db
def test_public_job_list_shows_only_open_jobs(client, company, job):
    Job.objects.create(company=company, title="Hidden draft")
    response = client.get(reverse("jobs:job_list"))
    assert response.status_code == 200
    assert b"Django Dev" in response.content
    assert b"Hidden draft" not in response.content


@pytest.mark.django_db
def test_public_job_list_search(client, job):
    response = client.get(reverse("jobs:job_list"), {"q": "django"})
    assert b"Django Dev" in response.content
    response = client.get(reverse("jobs:job_list"), {"q": "nothing-here"})
    assert b"Django Dev" not in response.content


@pytest.mark.django_db
def test_job_detail_404_for_draft(client, company):
    draft = Job.objects.create(company=company, title="Draft")
    assert client.get(reverse("jobs:job_detail", args=[draft.pk])).status_code == 404


@pytest.mark.django_db
def test_candidate_can_apply_via_post(client, job, candidate):
    client.force_login(candidate.user)
    response = client.post(reverse("jobs:job_apply", args=[job.pk]))
    assert response.status_code == 302
    app = Application.objects.get(job=job, candidate=candidate)
    assert app.current_stage == job.first_stage


@pytest.mark.django_db
def test_duplicate_apply_shows_error_and_creates_one(client, job, candidate):
    client.force_login(candidate.user)
    client.post(reverse("jobs:job_apply", args=[job.pk]))
    client.post(reverse("jobs:job_apply", args=[job.pk]), follow=True)
    assert Application.objects.filter(job=job, candidate=candidate).count() == 1


@pytest.mark.django_db
def test_apply_requires_login(client, job):
    response = client.post(reverse("jobs:job_apply", args=[job.pk]))
    assert response.status_code == 302
    assert "/accounts/" in response["Location"]


@pytest.mark.django_db
def test_my_applications_lists_own_only(client, job, candidate):
    client.force_login(candidate.user)
    client.post(reverse("jobs:job_apply", args=[job.pk]))
    response = client.get(reverse("jobs:my_applications"))
    assert b"Django Dev" in response.content


@pytest.mark.django_db
def test_recruiter_can_create_job_with_pipeline(client, recruiter, company):
    client.force_login(recruiter)
    response = client.post(
        reverse("jobs:manage_job_create"),
        {
            "title": "New Role",
            "location": "Remote",
            "description": "d",
            "requirements": "r",
            "employment_type": Job.FULL_TIME,
            "status": Job.OPEN,
        },
    )
    assert response.status_code == 302
    job = Job.objects.get(title="New Role")
    assert job.company == company
    assert job.stages.count() == 6
    assert job.created_by == recruiter


@pytest.mark.django_db
def test_manage_job_edit(client, recruiter, job):
    client.force_login(recruiter)
    response = client.post(
        reverse("jobs:manage_job_edit", args=[job.pk]),
        {
            "title": "Updated",
            "location": "",
            "description": "",
            "requirements": "",
            "employment_type": Job.CONTRACT,
            "status": Job.CLOSED,
        },
    )
    assert response.status_code == 302
    job.refresh_from_db()
    assert job.title == "Updated"
    assert job.status == Job.CLOSED


@pytest.mark.django_db
def test_manage_job_delete(client, owner, job):
    client.force_login(owner)
    response = client.post(reverse("jobs:manage_job_delete", args=[job.pk]))
    assert response.status_code == 302
    assert not Job.objects.filter(pk=job.pk).exists()


@pytest.mark.django_db
def test_stage_create_and_edit(client, recruiter, job):
    client.force_login(recruiter)
    client.post(
        reverse("jobs:stage_create", args=[job.pk]),
        {"name": "Panel", "order": 7, "kind": PipelineStage.INTERVIEW},
    )
    stage = job.stages.get(name="Panel")
    client.post(
        reverse("jobs:stage_edit", args=[job.pk, stage.pk]),
        {"name": "Panel 2", "order": 7, "kind": PipelineStage.INTERVIEW},
    )
    stage.refresh_from_db()
    assert stage.name == "Panel 2"


@pytest.mark.django_db
def test_stage_reorder(client, recruiter, job):
    client.force_login(recruiter)
    ids = list(job.stages.values_list("pk", flat=True))
    reversed_ids = list(reversed(ids))
    response = client.post(
        reverse("jobs:stage_reorder", args=[job.pk]), {"stage_ids": reversed_ids}
    )
    assert response.status_code == 302
    assert list(job.stages.order_by("order").values_list("pk", flat=True)) == reversed_ids


@pytest.mark.django_db
def test_stage_reorder_rejects_partial_list(client, recruiter, job):
    client.force_login(recruiter)
    first = job.stages.first()
    client.post(reverse("jobs:stage_reorder", args=[job.pk]), {"stage_ids": [first.pk]})
    assert list(job.stages.order_by("order").values_list("order", flat=True)) == [
        1, 2, 3, 4, 5, 6
    ]


@pytest.mark.django_db
def test_stage_delete(client, recruiter, job):
    client.force_login(recruiter)
    stage = job.stages.get(name="HR")
    client.post(reverse("jobs:stage_delete", args=[job.pk, stage.pk]))
    assert not job.stages.filter(pk=stage.pk).exists()


@pytest.mark.django_db
def test_skill_crud(client, recruiter, company):
    client.force_login(recruiter)
    client.post(reverse("jobs:skill_create"), {"name": "Python"})
    skill = Skill.objects.get(company=company, name="Python")
    client.post(reverse("jobs:skill_edit", args=[skill.pk]), {"name": "Django"})
    skill.refresh_from_db()
    assert skill.name == "Django"
    client.post(reverse("jobs:skill_delete", args=[skill.pk]))
    assert not Skill.objects.filter(pk=skill.pk).exists()


@pytest.mark.django_db
def test_duplicate_skill_rejected(client, recruiter, company):
    Skill.objects.create(company=company, name="Python")
    client.force_login(recruiter)
    client.post(reverse("jobs:skill_create"), {"name": "python"})
    assert Skill.objects.filter(company=company).count() == 1
