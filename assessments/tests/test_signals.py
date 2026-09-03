"""The post_save AI hook must be creation-only, key-gated and best-effort."""

import pytest

from assessments import signals
from jobs.models import Application


@pytest.mark.django_db
def test_no_key_skips_scoring(settings, job, candidate, monkeypatch):
    settings.ANTHROPIC_API_KEY = ""
    calls = []
    monkeypatch.setattr("assessments.ai.summarize_fit", lambda app: calls.append(app))
    Application.objects.create(job=job, candidate=candidate)
    assert calls == []


@pytest.mark.django_db
def test_scores_once_on_creation_only(settings, job, candidate, monkeypatch):
    settings.ANTHROPIC_API_KEY = "sk-test"
    calls = []
    monkeypatch.setattr("assessments.ai.summarize_fit", lambda app: calls.append(app.pk))
    application = Application.objects.create(job=job, candidate=candidate)
    assert calls == [application.pk]
    application.status = Application.REJECTED
    application.save()
    application.advance()
    assert calls == [application.pk]


@pytest.mark.django_db
def test_ai_failure_never_breaks_creation(settings, job, candidate, monkeypatch):
    settings.ANTHROPIC_API_KEY = "sk-test"

    def boom(application):
        raise RuntimeError("api down")

    monkeypatch.setattr("assessments.ai.summarize_fit", boom)
    application = Application.objects.create(job=job, candidate=candidate)
    assert application.pk is not None
    assert application.ai_fit_score is None


@pytest.mark.django_db
def test_score_application_helper_is_key_gated(settings, application, monkeypatch):
    settings.ANTHROPIC_API_KEY = ""
    monkeypatch.setattr("assessments.ai.summarize_fit", lambda app: 99)
    assert signals.score_application(application) is None
    settings.ANTHROPIC_API_KEY = "sk-test"
    assert signals.score_application(application) == 99
