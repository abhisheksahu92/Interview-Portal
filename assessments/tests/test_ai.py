"""AI wrapper tests. The Anthropic client is always mocked - no network."""

import json
from types import SimpleNamespace

import pytest

from assessments import ai
from assessments.models import Question
from core import llm


class FakeMessages:
    def __init__(self, payload, raises=False):
        self.payload = payload
        self.raises = raises
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise RuntimeError("boom")
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.payload)]
        )


def fake_client(monkeypatch, payload, raises=False):
    """Substitute the SDK client inside the shared provider layer.

    The modules no longer build their own client, so patching
    ``ai.get_client`` would silently no-op and let a real call escape.
    """
    messages = FakeMessages(payload, raises)
    monkeypatch.setattr(llm, "_anthropic_key", lambda: "test-key")
    monkeypatch.setattr(llm, "_anthropic_client", lambda: SimpleNamespace(messages=messages))
    return messages


@pytest.mark.django_db
def test_no_api_key_disables_ai(settings, job, skill, application, caplog):
    settings.ANTHROPIC_API_KEY = ""
    assert ai.get_client() is None
    assert ai.generate_questions(job, skill) == []
    assert ai.grade_text_answer(SimpleNamespace(text="q"), "a") is None
    assert ai.summarize_fit(application) is None
    application.refresh_from_db()
    assert application.ai_fit_score is None


@pytest.mark.django_db
def test_generate_questions_saves_mcqs(monkeypatch, job, skill):
    payload = json.dumps(
        {
            "questions": [
                {
                    "text": "What is a decorator?",
                    "options": ["a", "b", "c", "d"],
                    "correct_option": 2,
                    "difficulty": "hard",
                },
                {"text": "no options"},
            ]
        }
    )
    fake_client(monkeypatch, payload)
    created = ai.generate_questions(job, skill, n=2)
    assert len(created) == 1
    question = created[0]
    assert question.source == Question.AI
    assert question.company == job.company
    assert question.skill == skill
    assert question.correct_option == 2
    assert question.difficulty == Question.HARD


@pytest.mark.django_db
def test_generate_questions_text_kind_strips_options(monkeypatch, job, skill):
    fake_client(
        monkeypatch,
        "```json\n" + json.dumps({"questions": [{"text": "Explain WSGI.", "options": ["a"]}]}) + "\n```",
    )
    created = ai.generate_questions(job, skill, kind=Question.TEXT)
    assert len(created) == 1
    assert created[0].kind == Question.TEXT
    assert created[0].options == []
    assert created[0].correct_option is None


@pytest.mark.django_db
def test_api_failure_never_raises(monkeypatch, job, skill, application):
    fake_client(monkeypatch, "", raises=True)
    assert ai.generate_questions(job, skill) == []
    assert ai.grade_text_answer(SimpleNamespace(text="q"), "a") is None
    assert ai.summarize_fit(application) is None


@pytest.mark.django_db
def test_unparseable_response_returns_empty(monkeypatch, job, skill):
    fake_client(monkeypatch, "sorry, I cannot help")
    assert ai.generate_questions(job, skill) == []


@pytest.mark.django_db
def test_grade_text_answer_clamps(monkeypatch):
    fake_client(monkeypatch, json.dumps({"score": 250}))
    assert ai.grade_text_answer(SimpleNamespace(text="q"), "answer") == 100
    fake_client(monkeypatch, json.dumps({"score": -5}))
    assert ai.grade_text_answer(SimpleNamespace(text="q"), "answer") == 0
    assert ai.grade_text_answer(SimpleNamespace(text="q"), "") is None


@pytest.mark.django_db
def test_summarize_fit_sets_summary_and_score(monkeypatch, application):
    fake_client(
        monkeypatch, json.dumps({"fit_score": 77, "summary": "Strong Python match."})
    )
    assert ai.summarize_fit(application) == 77
    application.refresh_from_db()
    assert application.ai_fit_score == 77
    assert application.ai_summary == "Strong Python match."


@pytest.mark.django_db
def test_summarize_fit_prompt_includes_job_and_profile(monkeypatch, application):
    messages = fake_client(monkeypatch, json.dumps({"fit_score": 50, "summary": "ok"}))
    ai.summarize_fit(application)
    prompt = messages.calls[0]["messages"][0]["content"]
    assert "Backend Engineer" in prompt
    assert "3 years Python" in prompt
    assert "Python dev" in prompt
    assert messages.calls[0]["model"] == "claude-opus-5"


@pytest.mark.django_db
def test_extract_resume_text_best_effort(candidate, settings, tmp_path):
    from django.core.files.base import ContentFile

    settings.MEDIA_ROOT = tmp_path

    assert ai.extract_resume_text(candidate) == ""
    candidate.resume.save("cv.txt", ContentFile(b"Senior Python engineer"), save=True)
    assert "Senior Python engineer" in ai.extract_resume_text(candidate)


@pytest.mark.django_db
def test_summarize_fit_stores_structured_details(monkeypatch, application):
    fake_client(
        monkeypatch,
        json.dumps(
            {
                "fit_score": 82,
                "summary": "Good match. Missing AWS. Recommend a screen.",
                "strengths": ["5 years Python", {"name": "Django"}],
                "gaps": "No AWS exposure",
                "flagged_skills": ["AWS"],
            }
        ),
    )
    assert ai.summarize_fit(application) == 82
    application.refresh_from_db()
    details = application.ai_details
    assert details["fit_score"] == 82
    assert details["strengths"] == ["5 years Python", "Django"]
    assert details["gaps"] == ["No AWS exposure"]
    assert details["flagged_skills"] == ["AWS"]
    assert details["model"] == ai.MODEL
    assert details["scored_at"]
    assert details["resume_text_used"] is False


@pytest.mark.django_db
def test_summarize_fit_prompt_includes_resume_text(monkeypatch, application, tmp_path, settings):
    from django.core.files.base import ContentFile

    settings.MEDIA_ROOT = tmp_path
    profile = application.candidate
    profile.resume.save("cv.txt", ContentFile(b"Built Django REST services"), save=True)

    messages = fake_client(monkeypatch, json.dumps({"fit_score": 60, "summary": "ok"}))
    ai.summarize_fit(application)
    prompt = messages.calls[0]["messages"][0]["content"]
    assert "Built Django REST services" in prompt
    assert "flagged_skills" in prompt
    profile.refresh_from_db()
    assert profile.resume_parsed_at is not None
    application.refresh_from_db()
    assert application.ai_details["resume_text_used"] is True


@pytest.mark.django_db
def test_summarize_fit_no_structured_output_on_old_sdk(monkeypatch, application):
    """The mocked client has no ``messages.parse``, so no output_config is sent."""
    messages = fake_client(monkeypatch, json.dumps({"fit_score": 10, "summary": "x"}))
    ai.summarize_fit(application)
    assert "output_config" not in messages.calls[0]


@pytest.mark.django_db
def test_summarize_fit_uses_structured_output_when_supported(monkeypatch, application):
    messages = fake_client(monkeypatch, json.dumps({"fit_score": 30, "summary": "y"}))
    messages.parse = lambda **kwargs: None  # pretend the SDK supports it
    ai.summarize_fit(application)
    fmt = messages.calls[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["properties"]["fit_score"]["maximum"] == 100
