import datetime as dt

from django.core.management import call_command
from django.utils import timezone

from analytics.models import StageTransition
from core.models import Company, User
from jobs.models import Application, CandidateProfile, Job, PipelineStage


def _new_application(company=None):
    company = company or Company.objects.create(name="Signals Co")
    job = Job.objects.create(company=company, title="Dev", status=Job.OPEN)
    user = User.objects.create_user(email=f"c{User.objects.count()}@sig.test", password="pw12345678")
    candidate = CandidateProfile.objects.create(user=user)
    return Application.objects.create(
        job=job, candidate=candidate, current_stage=job.first_stage
    )


def test_creation_records_the_first_transition(db):
    app = _new_application()
    rows = list(app.stage_transitions.all())
    assert len(rows) == 1
    assert rows[0].from_stage_id is None
    assert rows[0].to_stage_id == app.current_stage_id
    assert rows[0].status_after == Application.ACTIVE


def test_advancing_records_a_stage_change(db):
    app = _new_application()
    first = app.current_stage
    app.advance()
    rows = list(app.stage_transitions.order_by("at", "id"))
    assert len(rows) == 2
    assert rows[1].from_stage_id == first.pk
    assert rows[1].to_stage.order == first.order + 1
    assert rows[1].status_after == Application.ACTIVE


def test_rejecting_records_a_status_change(db):
    app = _new_application()
    app.reject()
    last = app.stage_transitions.order_by("at", "id").last()
    assert last.status_after == Application.REJECTED
    assert last.from_stage_id == last.to_stage_id == app.current_stage_id


def test_saving_without_a_change_records_nothing(db):
    app = _new_application()
    app.ai_fit_score = 77
    app.save()
    assert app.stage_transitions.count() == 1


def test_hiring_at_the_last_stage_is_recorded(db):
    app = _new_application()
    for _ in range(PipelineStage.objects.filter(job=app.job).count()):
        app.advance()
    app.refresh_from_db()
    assert app.status == Application.HIRED
    assert app.stage_transitions.filter(status_after=Application.HIRED).exists()


def test_backfill_command_seeds_missing_history(db):
    app = _new_application()
    StageTransition.objects.all().delete()
    call_command("backfill_stage_transitions")
    rows = list(app.stage_transitions.all())
    assert len(rows) == 1
    assert rows[0].to_stage_id == app.current_stage_id
    assert rows[0].status_after == app.status


def test_backfill_command_is_idempotent(db):
    app = _new_application()
    call_command("backfill_stage_transitions")
    assert app.stage_transitions.count() == 1


def test_backfill_command_filters_by_company_and_dry_run(db):
    app = _new_application()
    other = _new_application(Company.objects.create(name="Untouched Co"))
    StageTransition.objects.all().delete()
    call_command("backfill_stage_transitions", company=app.job.company.slug, dry_run=True)
    assert StageTransition.objects.count() == 0
    call_command("backfill_stage_transitions", company=app.job.company.slug)
    assert app.stage_transitions.count() == 1
    assert other.stage_transitions.count() == 0


def test_transition_str_and_company(db):
    app = _new_application()
    row = app.stage_transitions.first()
    assert row.company == app.job.company
    assert str(app.current_stage_id) in str(row)
    assert row.at <= timezone.now() + dt.timedelta(seconds=1)
