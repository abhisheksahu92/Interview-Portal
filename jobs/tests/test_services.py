import pytest
from django.core.exceptions import ValidationError

from jobs.models import Application, Job, Skill, StageReview
from jobs.services import (
    advance_application,
    apply_to_job,
    create_job_with_default_stages,
    record_review,
)


@pytest.mark.django_db
def test_create_job_with_default_stages(company, owner):
    skill = Skill.objects.create(company=company, name="Python")
    job = create_job_with_default_stages(
        company=company, created_by=owner, skills=[skill], title="Backend Dev",
        status=Job.OPEN,
    )
    assert job.stages.count() == 6
    assert list(job.skills.all()) == [skill]
    assert job.created_by == owner


@pytest.mark.django_db
def test_apply_to_job_sets_first_stage(job, candidate):
    app = apply_to_job(job, candidate)
    assert app.status == Application.ACTIVE
    assert app.current_stage == job.first_stage


@pytest.mark.django_db
def test_apply_to_draft_job_rejected(company, candidate):
    draft = Job.objects.create(company=company, title="Draft role")
    with pytest.raises(ValidationError):
        apply_to_job(draft, candidate)


@pytest.mark.django_db
def test_apply_twice_rejected(job, candidate):
    apply_to_job(job, candidate)
    with pytest.raises(ValidationError):
        apply_to_job(job, candidate)


@pytest.mark.django_db
def test_pass_review_advances_application(job, candidate, interviewer):
    app = apply_to_job(job, candidate)
    review = record_review(
        app, app.current_stage, interviewer, StageReview.PASS, rating=4, feedback="good"
    )
    app.refresh_from_db()
    assert review.decision == StageReview.PASS
    assert app.current_stage.name == "Assessment"


@pytest.mark.django_db
def test_fail_review_rejects_application(job, candidate, recruiter):
    app = apply_to_job(job, candidate)
    record_review(app, app.current_stage, recruiter, StageReview.FAIL)
    app.refresh_from_db()
    assert app.status == Application.REJECTED


@pytest.mark.django_db
def test_hold_review_leaves_application_in_place(job, candidate, interviewer):
    app = apply_to_job(job, candidate)
    record_review(app, app.current_stage, interviewer, StageReview.HOLD)
    app.refresh_from_db()
    assert app.status == Application.ACTIVE
    assert app.current_stage.name == "Screening"


@pytest.mark.django_db
def test_review_by_outsider_does_not_advance(job, candidate, other_recruiter):
    app = apply_to_job(job, candidate)
    record_review(app, app.current_stage, other_recruiter, StageReview.PASS)
    app.refresh_from_db()
    assert app.current_stage.name == "Screening"


@pytest.mark.django_db
def test_review_at_non_current_stage_does_not_advance(job, candidate, interviewer):
    app = apply_to_job(job, candidate)
    later = job.stages.get(name="HR")
    record_review(app, later, interviewer, StageReview.PASS)
    app.refresh_from_db()
    assert app.current_stage.name == "Screening"


@pytest.mark.django_db
def test_review_for_foreign_stage_raises(job, candidate, interviewer, company):
    other_job = Job.objects.create(company=company, title="Other", status=Job.OPEN)
    app = apply_to_job(job, candidate)
    with pytest.raises(ValidationError):
        record_review(app, other_job.first_stage, interviewer, StageReview.PASS)


@pytest.mark.django_db
def test_pass_at_last_stage_hires(job, candidate, interviewer):
    app = apply_to_job(job, candidate)
    for _ in range(5):
        advance_application(app)
    assert app.current_stage.name == "Offer"
    record_review(app, app.current_stage, interviewer, StageReview.PASS)
    app.refresh_from_db()
    assert app.status == Application.HIRED


@pytest.mark.django_db
def test_review_is_updated_not_duplicated(job, candidate, interviewer):
    app = apply_to_job(job, candidate)
    stage = app.current_stage
    record_review(app, stage, interviewer, StageReview.HOLD, feedback="wait")
    record_review(app, stage, interviewer, StageReview.HOLD, feedback="still waiting")
    assert app.reviews.count() == 1
    assert app.reviews.first().feedback == "still waiting"
