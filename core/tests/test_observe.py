"""Tests for KAN-10: hiring pipeline observability (core/observe.py)."""

import logging
from django.test import TestCase


class HiringEventTest(TestCase):
    def test_hiring_event_emits_log(self):
        from core.observe import hiring_event

        with self.assertLogs("hiring", level="INFO") as cm:
            hiring_event("application.created", application_id=1, job_id=2)

        self.assertTrue(any("application.created" in line for line in cm.output))
        self.assertTrue(any("application_id=1" in line for line in cm.output))
        self.assertTrue(any("job_id=2" in line for line in cm.output))

    def test_hiring_event_with_sentry_absent_does_not_raise(self):
        """hiring_event should never raise even when sentry_sdk is not importable."""
        import sys
        import unittest.mock as mock

        from core.observe import hiring_event

        with mock.patch.dict(sys.modules, {"sentry_sdk": None}):
            # Should not raise
            hiring_event("test.event", key="value")

    def test_timed_hiring_event_logs_start_and_finish(self):
        from core.observe import timed_hiring_event

        with self.assertLogs("hiring", level="INFO") as cm:
            with timed_hiring_event("ai.scoring", application_id=99):
                pass

        lines = " ".join(cm.output)
        self.assertIn("ai.scoring.started", lines)
        self.assertIn("ai.scoring.finished", lines)
        self.assertIn("outcome=ok", lines)
        self.assertIn("duration_ms=", lines)

    def test_timed_hiring_event_logs_error_on_exception(self):
        from core.observe import timed_hiring_event

        with self.assertLogs("hiring", level="INFO") as cm:
            try:
                with timed_hiring_event("ai.scoring", application_id=99):
                    raise ValueError("boom")
            except ValueError:
                pass

        lines = " ".join(cm.output)
        self.assertIn("outcome=error", lines)
