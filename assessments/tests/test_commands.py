"""rescore_applications management command."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from jobs.models import Application


def run(*args):
    out = StringIO()
    call_command("rescore_applications", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


@pytest.mark.django_db
def test_requires_a_selector():
    with pytest.raises(CommandError):
        run()


@pytest.mark.django_db
def test_all_rescores_every_application(monkeypatch, application):
    scored = []

    def fake(app):
        scored.append(app.pk)
        app.ai_fit_score = 71
        app.save(update_fields=["ai_fit_score"])
        return 71

    monkeypatch.setattr("assessments.ai.summarize_fit", fake)
    output = run("--all")
    assert scored == [application.pk]
    assert "Scored 1/1" in output
    application.refresh_from_db()
    assert application.ai_fit_score == 71


@pytest.mark.django_db
def test_company_and_job_filters(monkeypatch, application, other_company, candidate):
    from jobs.models import Job

    other_job = Job.objects.create(company=other_company, title="Other role")
    other_application = Application.objects.create(job=other_job, candidate=candidate)

    scored = []
    monkeypatch.setattr("assessments.ai.summarize_fit", lambda app: scored.append(app.pk) or 50)

    run("--company", application.job.company.slug)
    assert scored == [application.pk]

    scored.clear()
    run("--job", str(other_job.pk))
    assert scored == [other_application.pk]


@pytest.mark.django_db
def test_missing_only_and_no_matches(monkeypatch, application):
    application.ai_fit_score = 40
    application.save(update_fields=["ai_fit_score"])
    monkeypatch.setattr("assessments.ai.summarize_fit", lambda app: 1)
    assert "No matching applications." in run("--all", "--missing-only")


@pytest.mark.django_db
def test_failures_are_counted(monkeypatch, application):
    monkeypatch.setattr("assessments.ai.summarize_fit", lambda app: None)
    assert "Scored 0/1 applications (1 skipped)." in run("--all")
