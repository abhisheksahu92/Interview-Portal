"""Tests for dedicated background worker process."""

from io import StringIO
from unittest.mock import patch
import pytest
from django.core.management import call_command

from core.queue import enqueue


def dummy_job(x, y):
    return x + y


def failing_job():
    raise RuntimeError("Intentional task failure")


@pytest.mark.django_db
def test_worker_burst_empty():
    out = StringIO()
    call_command("run_worker", burst=True, stdout=out)
    output = out.getvalue()
    assert "Starting background worker" in output
    assert "Worker shutdown gracefully" in output


@pytest.mark.django_db
def test_worker_processes_enqueued_task():
    # Enqueue a task
    out = StringIO()
    with patch("core.management.commands.run_worker.dequeue") as mock_dequeue:
        # First call returns task, second returns None
        mock_dequeue.side_effect = [
            {
                "id": "task-test-1",
                "func": "core.tests.test_worker.dummy_job",
                "args": [10, 20],
                "kwargs": {},
                "queue": "default",
            },
            None,
        ]
        call_command("run_worker", burst=True, stdout=out)

    output = out.getvalue()
    assert "OK   core.tests.test_worker.dummy_job" in output
    assert "Total tasks processed: 1" in output


@pytest.mark.django_db
def test_worker_handles_and_reports_task_exception():
    out = StringIO()
    with patch("core.management.commands.run_worker.dequeue") as mock_dequeue:
        mock_dequeue.side_effect = [
            {
                "id": "task-err-1",
                "func": "core.tests.test_worker.failing_job",
                "args": [],
                "kwargs": {},
                "queue": "ai",
            },
            None,
        ]
        call_command("run_worker", burst=True, stdout=out)

    output = out.getvalue()
    assert "FAIL core.tests.test_worker.failing_job" in output
    assert "Intentional task failure" in output
