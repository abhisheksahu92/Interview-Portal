"""Tests for the KAN-9 AI provider gateway (core/llm.py)."""

import json
import unittest.mock as mock
from django.core.cache import cache
from django.test import TestCase, override_settings

import core.llm as llm


def _clear_all_cooldowns():
    for name in llm._PROVIDER_CHAIN:
        cache.delete(llm._COOLDOWN_KEY.format(provider=name))


class CircuitBreakerTest(TestCase):
    def setUp(self):
        _clear_all_cooldowns()

    def test_mark_and_check_cooling_down(self):
        self.assertFalse(llm._is_provider_cooling_down("anthropic"))
        llm._mark_provider_cooling_down("anthropic", 60)
        self.assertTrue(llm._is_provider_cooling_down("anthropic"))
        llm._clear_provider_cooldown("anthropic")
        self.assertFalse(llm._is_provider_cooling_down("anthropic"))

    def test_active_provider_skips_cooling_down(self):
        _clear_all_cooldowns()
        llm._mark_provider_cooling_down("anthropic", 60)
        llm._mark_provider_cooling_down("gemini", 60)
        # Patch key functions to make anthropic/gemini appear configured
        with mock.patch("core.llm._anthropic_key", return_value="key-a"):
            with mock.patch("core.llm._gemini_key", return_value="key-g"):
                provider = llm.active_provider()
        # Both cooling down, should fall to ollama
        self.assertEqual(provider, "ollama")
        _clear_all_cooldowns()

    def test_active_provider_empty_when_nothing_configured(self):
        _clear_all_cooldowns()
        with mock.patch("core.llm._anthropic_key", return_value=""):
            with mock.patch("core.llm._gemini_key", return_value=""):
                with mock.patch("core.llm._ollama_enabled", return_value=False):
                    self.assertEqual(llm.active_provider(), "")
                    self.assertFalse(llm.is_configured())


class FallbackChainTest(TestCase):
    """Chain tests use explicit key mocks instead of override_settings so they
    work correctly under pytest-xdist workers."""

    def setUp(self):
        _clear_all_cooldowns()

    def _standard_patches(self):
        """Patches that make anthropic and gemini appear configured."""
        return [
            mock.patch("core.llm._anthropic_key", return_value="key-a"),
            mock.patch("core.llm._gemini_key", return_value="key-g"),
        ]

    def test_complete_uses_anthropic_first(self):
        _clear_all_cooldowns()
        with mock.patch("core.llm._anthropic_key", return_value="key-a"):
            with mock.patch("core.llm._gemini_key", return_value="key-g"):
                with mock.patch("core.llm._complete_anthropic", return_value="result-a") as ma:
                    with mock.patch("core.llm._complete_gemini", return_value="result-g"):
                        with mock.patch("core.llm._complete_ollama", return_value="result-o"):
                            result = llm.complete("hello")
        self.assertEqual(result, "result-a")
        ma.assert_called_once()

    def test_complete_falls_back_to_gemini_when_anthropic_rate_limited(self):
        _clear_all_cooldowns()

        def anthropic_rate_limit(*args, **kwargs):
            raise llm._ProviderRateLimited("anthropic")

        with mock.patch("core.llm._anthropic_key", return_value="key-a"):
            with mock.patch("core.llm._gemini_key", return_value="key-g"):
                with mock.patch("core.llm._complete_anthropic", side_effect=anthropic_rate_limit):
                    with mock.patch("core.llm._complete_gemini", return_value="result-g") as mg:
                        with mock.patch("core.llm._complete_ollama", return_value="result-o"):
                            result = llm.complete("hello")

        self.assertEqual(result, "result-g")
        self.assertTrue(llm._is_provider_cooling_down("anthropic"))
        mg.assert_called_once()

    def test_complete_falls_back_to_ollama_when_both_cloud_cooling_down(self):
        _clear_all_cooldowns()
        llm._mark_provider_cooling_down("anthropic", 60)
        llm._mark_provider_cooling_down("gemini", 60)

        with mock.patch("core.llm._anthropic_key", return_value="key-a"):
            with mock.patch("core.llm._gemini_key", return_value="key-g"):
                with mock.patch("core.llm._complete_ollama", return_value="result-local") as mo:
                    result = llm.complete("hello")

        self.assertEqual(result, "result-local")
        mo.assert_called_once()

    def test_complete_returns_none_when_all_exhausted(self):
        _clear_all_cooldowns()
        llm._mark_provider_cooling_down("anthropic", 60)
        llm._mark_provider_cooling_down("gemini", 60)
        llm._mark_provider_cooling_down("ollama", 60)

        with mock.patch("core.llm._anthropic_key", return_value="key-a"):
            with mock.patch("core.llm._gemini_key", return_value="key-g"):
                result = llm.complete("hello")

        self.assertIsNone(result)

    def test_complete_clears_cooldown_after_success(self):
        _clear_all_cooldowns()
        llm._mark_provider_cooling_down("anthropic", 60)
        llm._mark_provider_cooling_down("gemini", 60)

        with mock.patch("core.llm._anthropic_key", return_value="key-a"):
            with mock.patch("core.llm._gemini_key", return_value="key-g"):
                with mock.patch("core.llm._complete_ollama", return_value="ok"):
                    llm.complete("hello")

        self.assertFalse(llm._is_provider_cooling_down("ollama"))


class OllamaBackendTest(TestCase):
    def setUp(self):
        _clear_all_cooldowns()

    def test_ollama_backend_parses_response(self):
        fake_payload = {"response": "hello world"}
        mock_ctx = mock.MagicMock()
        mock_ctx.__enter__ = lambda s: s
        mock_ctx.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch("urllib.request.urlopen", return_value=mock_ctx):
            with mock.patch("json.load", return_value=fake_payload):
                result = llm._complete_ollama("", "test prompt", 256, "")
        self.assertEqual(result, "hello world")

    def test_ollama_strips_think_tags(self):
        fake_payload = {"response": "<think>reasoning</think>answer"}
        mock_ctx = mock.MagicMock()
        mock_ctx.__enter__ = lambda s: s
        mock_ctx.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch("urllib.request.urlopen", return_value=mock_ctx):
            with mock.patch("json.load", return_value=fake_payload):
                result = llm._complete_ollama("", "test", 256, "deepseek-r1:7b")
        self.assertEqual(result, "answer")

    def test_ollama_returns_none_on_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = llm._complete_ollama("", "test", 256, "")
        self.assertIsNone(result)
