"""Validation and role-gating guards in jobs.services.

These live apart from ``test_services.py`` (happy-path transitions) and keep the
service layer covered now that the jobs app ships no views of its own.
"""

import pytest
from django.core.exceptions import ValidationError

from core.models import User
from jobs.models import Application, Job, StageReview
from jobs.services import apply_to_job, record_review


@pytest.mark.django_db
def test_apply_to_closed_job_rejected(company, candidate):
    closed = Job.objects.create(company=company, title="Filled role", status=Job.CLOSED)
    with pytest.raises(ValidationError) as exc:
        apply_to_job(closed, candidate)
    assert "not open" in " ".join(exc.value.messages).lower()
    assert not Application.objects.filter(job=closed).exists()


@pytest.mark.django_db
def test_duplicate_apply_leaves_a_single_application(job, candidate):
    first = apply_to_job(job, candidate)
    with pytest.raises(ValidationError) as exc:
        apply_to_job(job, candidate)
    assert "already applied" in " ".join(exc.value.messages).lower()
    assert list(Application.objects.filter(job=job, candidate=candidate)) == [first]


@pytest.mark.django_db
def test_review_by_user_without_membership_does_not_advance(job, candidate):
    """A recorded review is kept, but only a company role may move the pipeline."""
    outsider = User.objects.create_user(email="nobody@example.test", password="pw12345678")
    app = apply_to_job(job, candidate)
    review = record_review(app, app.current_stage, outsider, StageReview.PASS)
    app.refresh_from_db()
    assert review.pk is not None
    assert app.status == Application.ACTIVE
    assert app.current_stage.name == "Screening"


@pytest.mark.django_db
def test_fail_review_without_membership_does_not_reject(job, candidate):
    outsider = User.objects.create_user(email="nobody2@example.test", password="pw12345678")
    app = apply_to_job(job, candidate)
    record_review(app, app.current_stage, outsider, StageReview.FAIL)
    app.refresh_from_db()
    assert app.status == Application.ACTIVE


@pytest.mark.django_db
def test_review_on_inactive_application_does_not_transition(job, candidate, recruiter):
    app = apply_to_job(job, candidate)
    app.reject()
    record_review(app, app.current_stage, recruiter, StageReview.PASS)
    app.refresh_from_db()
    assert app.status == Application.REJECTED
