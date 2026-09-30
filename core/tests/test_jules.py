"""Tests for Google Jules integration and automated bug-fixing pipeline (core/jules.py)."""

from unittest import mock
from django.core.cache import cache
from django.test import TestCase, override_settings

from core import jules


class JulesClientTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(JULES_KEY="")
    def test_not_configured_when_key_empty(self):
        self.assertFalse(jules.is_configured())
        self.assertEqual(jules.list_sessions(), [])
        self.assertIsNone(jules.create_session("Do work"))
        self.assertIsNone(jules.dispatch_bug_fix_task("Err", "Summary"))

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

    @override_settings(JULES_KEY="fake-jules-key")
    @mock.patch("core.slack.send_slack_message")
    @mock.patch("core.queue.enqueue")
    def test_dispatch_bug_fix_task_creates_session_and_deduplicates(self, mock_enqueue, mock_slack):
        with mock.patch("core.jules.create_session") as mock_create:
            mock_create.return_value = {
                "name": "sessions/test-999",
                "url": "https://jules.google.com/session/test-999",
            }

            # 1. First dispatch succeeds
            res1 = jules.dispatch_bug_fix_task(
                title="ZeroDivisionError",
                error_summary="division by zero",
                traceback_str="line 42",
                path="/api/calc",
            )
            self.assertIsNotNone(res1)
            mock_slack.assert_called_once()
            mock_enqueue.assert_called_once_with(
                "core.jules.poll_jules_session",
                session_id="sessions/test-999",
                error_title="Fix: ZeroDivisionError",
                poll_count=0,
            )

            # 2. Second dispatch for the same error within 1 hour is deduplicated (no-op)
            mock_create.reset_mock()
            mock_slack.reset_mock()
            res2 = jules.dispatch_bug_fix_task(
                title="ZeroDivisionError",
                error_summary="division by zero",
                traceback_str="line 42",
                path="/api/calc",
            )
            self.assertIsNone(res2)
            mock_create.assert_not_called()
            mock_slack.assert_not_called()

    @override_settings(JULES_KEY="fake-jules-key")
    @mock.patch("core.slack.send_slack_message")
    def test_poll_jules_session_completed_notifies_slack(self, mock_slack):
        completed_activity = {
            "name": "sessions/123/activities/act-1",
            "originator": "agent",
            "sessionCompleted": {},
            "artifacts": [
                {
                    "changeSet": {
                        "gitPatch": {
                            "suggestedCommitMessage": "Fix ZeroDivisionError in calculation endpoint"
                        }
                    }
                }
            ],
        }

        with mock.patch("core.jules.list_activities", return_value=[completed_activity]):
            jules.poll_jules_session(session_id="sessions/123", error_title="ZeroDivisionError")

        mock_slack.assert_called_once()
        args, kwargs = mock_slack.call_args
        self.assertEqual(args[0], "system_errors")
        self.assertIn("Jules AI Completed Fix", args[1])
        self.assertIn("Fix ZeroDivisionError", args[1])

    @override_settings(JULES_KEY="fake-jules-key")
    @mock.patch("core.slack.send_slack_message")
    def test_poll_jules_session_question_notifies_slack(self, mock_slack):
        question_activity = {
            "name": "sessions/123/activities/act-2",
            "originator": "agent",
            "question": {"text": "Should we return 0 or None when denominator is zero?"},
        }

        with mock.patch("core.jules.list_activities", return_value=[question_activity]):
            jules.poll_jules_session(session_id="sessions/123", error_title="ZeroDivisionError")

        mock_slack.assert_called_once()
        args, kwargs = mock_slack.call_args
        self.assertEqual(args[0], "system_errors")
        self.assertIn("Jules AI Needs Clarification", args[1])
