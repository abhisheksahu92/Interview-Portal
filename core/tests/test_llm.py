"""Provider selection for the shared LLM layer.

The point of this module is that AI features keep working when the customer
has a Gemini key but no Anthropic one, so the selection rules are pinned here.
"""

import json
from types import SimpleNamespace

import pytest

from core import llm


def test_no_keys_means_no_provider(settings):
    settings.ANTHROPIC_API_KEY = ""
    settings.GEMINI_API_KEY = ""

    assert llm.active_provider() == ""
    assert llm.is_configured() is False
    assert llm.complete("hi") is None


def test_gemini_is_used_when_it_is_the_only_key(settings):
    settings.ANTHROPIC_API_KEY = ""
    settings.GEMINI_API_KEY = "AIza-test"

    assert llm.active_provider() == "gemini"
    assert llm.is_configured() is True


def test_anthropic_wins_when_both_are_set(settings):
    """Prompts were tuned against Anthropic, so it takes precedence."""
    settings.ANTHROPIC_API_KEY = "sk-test"
    settings.GEMINI_API_KEY = "AIza-test"

    assert llm.active_provider() == "anthropic"


def test_gemini_response_text_is_returned(settings, monkeypatch):
    settings.ANTHROPIC_API_KEY = ""
    settings.GEMINI_API_KEY = "AIza-test"
    payload = {"candidates": [{"content": {"parts": [{"text": '{"score": 88}'}]}}]}

    class FakeResponse:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *a, **k: FakeResponse())

    assert llm.complete("grade this") == '{"score": 88}'


def test_a_blocked_gemini_response_degrades_to_none(settings, monkeypatch):
    """A safety block returns candidates without content; never raise."""
    settings.ANTHROPIC_API_KEY = ""
    settings.GEMINI_API_KEY = "AIza-test"

    class FakeResponse:
        def read(self):
            return json.dumps({"candidates": [{"finishReason": "SAFETY"}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *a, **k: FakeResponse())

    assert llm.complete("anything") is None


def test_anthropic_failure_degrades_to_none(settings, monkeypatch):
    settings.ANTHROPIC_API_KEY = "sk-test"

    def boom(**kwargs):
        raise RuntimeError("api down")

    monkeypatch.setattr(
        llm, "_anthropic_client", lambda: SimpleNamespace(messages=SimpleNamespace(create=boom))
    )

    assert llm.complete("anything") is None


@pytest.mark.parametrize("provider_key", ["ANTHROPIC_API_KEY", "GEMINI_API_KEY"])
def test_whitespace_only_keys_do_not_count_as_configured(settings, provider_key):
    settings.ANTHROPIC_API_KEY = ""
    settings.GEMINI_API_KEY = ""
    setattr(settings, provider_key, "   ")

    assert llm.is_configured() is False
