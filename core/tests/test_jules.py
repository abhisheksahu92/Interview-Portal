"""Tests for Google Jules integration (core/jules.py)."""

from unittest import mock
from django.test import TestCase, override_settings
from core import jules


class JulesClientTests(TestCase):
    @override_settings(JULES_KEY="")
    def test_not_configured_when_key_empty(self):
        self.assertFalse(jules.is_configured())
        self.assertEqual(jules.list_sessions(), [])
        self.assertIsNone(jules.create_session("Do work"))

    @override_settings(JULES_KEY="fake-jules-key")
    def test_configured_when_key_present(self):
        self.assertTrue(jules.is_configured())

    @override_settings(JULES_KEY="fake-jules-key")
    def test_list_sessions_makes_authenticated_request(self):
        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = b'{"sessions": [{"name": "sessions/123", "state": "IN_PROGRESS"}]}'
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            sessions = jules.list_sessions()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["name"], "sessions/123")
