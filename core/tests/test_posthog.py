"""Tests for KAN-11: PostHog server-side analytics (core/analytics.py)."""

import unittest.mock as mock
from django.test import TestCase, override_settings


class CaptureTest(TestCase):
    def _reset_client(self):
        """Reset the module-level singleton so override_settings takes effect."""
        import core.analytics as m
        m._client = None

    def setUp(self):
        self._reset_client()

    def tearDown(self):
        self._reset_client()

    @override_settings(POSTHOG_KEY="", POSTHOG_HOST="https://eu.i.posthog.com")
    def test_capture_noop_when_no_key(self):
        from core.analytics import capture
        # Should not raise and should not call any PostHog client
        with mock.patch("posthog.Posthog") as MockClient:
            capture("user-1", "test_event", {"foo": "bar"})
        MockClient.assert_not_called()

    @override_settings(POSTHOG_KEY="phc_testkey", POSTHOG_HOST="https://eu.i.posthog.com")
    def test_capture_calls_posthog_client(self):
        from core.analytics import capture, _get_client
        import core.analytics as m

        mock_client = mock.MagicMock()
        m._client = mock_client

        capture("42", "application_submitted", {"job_id": 7})
        mock_client.capture.assert_called_once_with(
            distinct_id="42",
            event="application_submitted",
            properties={"job_id": 7},
        )

    def test_capture_never_raises_on_exception(self):
        import core.analytics as m

        mock_client = mock.MagicMock()
        mock_client.capture.side_effect = Exception("network error")
        m._client = mock_client

        # Should not raise
        from core.analytics import capture
        capture("42", "test_event")

    def test_identify_never_raises_on_exception(self):
        import core.analytics as m

        mock_client = mock.MagicMock()
        mock_client.identify.side_effect = Exception("network error")
        m._client = mock_client

        from core.analytics import identify
        identify("42", {"plan": "pro"})

    @override_settings(POSTHOG_KEY="phc_testkey")
    def test_identify_calls_posthog_client(self):
        import core.analytics as m

        mock_client = mock.MagicMock()
        m._client = mock_client

        from core.analytics import identify
        identify("99", {"plan": "starter"})
        mock_client.identify.assert_called_once_with(
            distinct_id="99",
            properties={"plan": "starter"},
        )
