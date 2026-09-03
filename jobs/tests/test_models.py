import pytest
from django.db import IntegrityError

from jobs.models import Application, Job, PipelineStage, Skill


@pytest.mark.django_db
def test_job_creation_seeds_default_stages(company):
    job = Job.objects.create(company=company, title="QA Engineer")
    names = list(job.stages.values_list("name", flat=True))
    assert names == ["Screening", "Assessment", "L1 Interview", "L2 Interview", "HR", "Offer"]
    assert list(job.stages.values_list("order", flat=True)) == [1, 2, 3, 4, 5, 6]
    assert job.stages.get(name="Assessment").requires_assessment is True
    assert job.stages.get(name="Screening").kind == PipelineStage.SCREENING


@pytest.mark.django_db
def test_saving_job_again_does_not_duplicate_stages(job):
    job.title = "Renamed"
    job.save()
    assert job.stages.count() == 6


@pytest.mark.django_db
def test_skill_unique_per_company(company, other_company):
    Skill.objects.create(company=company, name="Python")
    Skill.objects.create(company=other_company, name="Python")
    with pytest.raises(IntegrityError):
        Skill.objects.create(company=company, name="Python")


@pytest.mark.django_db
def test_stage_order_unique_per_job(job):
    with pytest.raises(IntegrityError):
        PipelineStage.objects.create(job=job, name="Dup", order=1)


@pytest.mark.django_db
def test_application_advance_walks_pipeline_then_hires(job, candidate):
    app = Application.objects.create(job=job, candidate=candidate, current_stage=job.first_stage)
    assert app.company == job.company
    for expected in ["Assessment", "L1 Interview", "L2 Interview", "HR", "Offer"]:
        app.advance()
        assert app.current_stage.name == expected
    app.advance()
    assert app.status == Application.HIRED
    assert app.current_stage.name == "Offer"


@pytest.mark.django_db
def test_application_reject(job, candidate):
    app = Application.objects.create(job=job, candidate=candidate, current_stage=job.first_stage)
    app.reject()
    app.refresh_from_db()
    assert app.status == Application.REJECTED


@pytest.mark.django_db
def test_advance_is_noop_for_inactive_application(job, candidate):
    app = Application.objects.create(job=job, candidate=candidate, current_stage=job.first_stage)
    app.reject()
    app.advance()
    assert app.status == Application.REJECTED
    assert app.current_stage.name == "Screening"


@pytest.mark.django_db
def test_application_unique_per_job_and_candidate(job, candidate):
    Application.objects.create(job=job, candidate=candidate)
    with pytest.raises(IntegrityError):
        Application.objects.create(job=job, candidate=candidate)
