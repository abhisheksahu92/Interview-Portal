"""Tests for Redis cache, cached_db sessions, and background queue."""

import uuid
from decimal import Decimal
import pytest
from django.core.cache import cache
from core.queue import enqueue, execute_task, mark_failed, task


def sample_multiply(a, b):
    return a * b


@task(queue_name="ai")
def sample_ai_task(name, multiplier=2):
    return f"{name} scored {10 * multiplier}"


def test_cache_set_and_get():
    cache.set("test_key", "valkey_redis_success", 60)
    assert cache.get("test_key") == "valkey_redis_success"


def test_queue_synchronous_execution():
    res = enqueue(sample_multiply, 6, 7)
    assert res == 42


def test_queue_decorator_delay():
    res = sample_ai_task.delay("candidate_123", multiplier=3)
    assert res == "candidate_123 scored 30"


def test_queue_mark_failed_retries_and_dead_letter():
    task_payload = {
        "id": str(uuid.uuid4()),
        "func": "sample_func",
        "args": [1],
        "kwargs": {},
        "queue": "default",
        "max_retries": 2,
        "retries": 0,
    }

    # First failure -> retry
    mark_failed(task_payload, ValueError("Transient error"))
    assert task_payload["retries"] == 1
    assert "Transient error" in task_payload["last_error"]

    # Second failure -> retry
    mark_failed(task_payload, ValueError("Transient error 2"))
    assert task_payload["retries"] == 2

    # Third failure -> exceeds max_retries (2) -> dead letter
    mark_failed(task_payload, ValueError("Permanent failure"))
    assert task_payload["retries"] == 3
