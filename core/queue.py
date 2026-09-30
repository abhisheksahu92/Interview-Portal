"""Lightweight Redis / Valkey background job queue for Interview Portal.

Designed for Render zero-overhead worker processes, supporting:
- Multiple named queues: default, ai, notifications, webhooks, scheduled
- Delayed execution / countdown
- Exponential backoff retries and Dead Letter Queue (DLQ)
- Dynamic task import & @task decorator
- Graceful in-process synchronous fallback during pytest / local dev
"""

import importlib
import json
import logging
import time
import uuid
from datetime import date, datetime
from decimal import Decimal
from functools import wraps

from django.conf import settings

logger = logging.getLogger(__name__)

# Registry of task functions
_TASK_REGISTRY = {}


class QueueJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder handling UUIDs, datetimes, and Decimals."""

    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, (Decimal, uuid.UUID)):
            return str(obj)
        return super().default(obj)


def get_redis_client():
    """Return a configured Redis client, or None if unavailable / testing."""
    if getattr(settings, "TESTING", False) or getattr(settings, "QUEUE_SYNCHRONOUS", False):
        return None
    redis_url = getattr(settings, "REDIS_URL", "")
    if not redis_url:
        return None
    try:
        import redis
        client = redis.from_url(redis_url, decode_responses=True, socket_timeout=5)
        client.ping()
        return client
    except Exception as e:
        logger.warning("Redis queue client unavailable (%s); falling back to synchronous execution.", e)
        return None


def task(queue_name="default", max_retries=3):
    """Decorator to register a function as a background task.

    Provides a ``.delay(*args, **kwargs)`` helper to enqueue the task.
    """

    def decorator(fn):
        func_path = f"{fn.__module__}.{fn.__qualname__}"
        _TASK_REGISTRY[func_path] = fn

        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        def delay(*args, **kwargs):
            countdown = kwargs.pop("countdown", 0)
            return enqueue(
                func_path,
                *args,
                queue=queue_name,
                countdown=countdown,
                max_retries=max_retries,
                **kwargs,
            )

        wrapper.delay = delay
        wrapper.task_path = func_path
        return wrapper

    return decorator


def enqueue(func_or_path, *args, queue="default", countdown=0, max_retries=3, **kwargs):
    """Enqueue a function or dotted path to be executed asynchronously."""
    if callable(func_or_path):
        func_path = f"{func_or_path.__module__}.{func_or_path.__qualname__}"
        _TASK_REGISTRY[func_path] = func_or_path
    else:
        func_path = str(func_or_path)

    task_id = str(uuid.uuid4())
    task_payload = {
        "id": task_id,
        "func": func_path,
        "args": list(args),
        "kwargs": kwargs,
        "queue": queue,
        "max_retries": max_retries,
        "retries": 0,
        "created_at": time.time(),
        "eta": time.time() + countdown,
    }

    client = get_redis_client()
    if client is None:
        # Synchronous execution fallback (e.g. pytest or local dev without Redis)
        logger.info("Executing task %s (%s) synchronously", task_id, func_path)
        return execute_task(task_payload)

    serialized = json.dumps(task_payload, cls=QueueJSONEncoder)
    if countdown > 0:
        # Scheduled task using sorted set (ZSET) scored by target unix timestamp
        client.zadd(f"queue:delayed:{queue}", {serialized: task_payload["eta"]})
        logger.debug("Scheduled task %s for queue %s in %ss", task_id, queue, countdown)
    else:
        client.rpush(f"queue:{queue}", serialized)
        logger.debug("Enqueued task %s to queue %s", task_id, queue)

    return task_id


def dequeue(queues=None, timeout=2):
    """Pop the next available task from the specified queues.

    Also moves ready delayed tasks into their respective immediate queues.
    """
    client = get_redis_client()
    if not client:
        return None

    if queues is None:
        queues = ["ai", "notifications", "webhooks", "scheduled", "default"]

    now = time.time()
    # Check delayed queues and move matured tasks to ready lists
    for q in queues:
        delayed_key = f"queue:delayed:{q}"
        ready_tasks = client.zrangebyscore(delayed_key, 0, now)
        if ready_tasks:
            pipe = client.pipeline()
            for t_json in ready_tasks:
                pipe.zrem(delayed_key, t_json)
                pipe.rpush(f"queue:{q}", t_json)
            pipe.execute()

    # Block-pop from active queues in priority order
    queue_keys = [f"queue:{q}" for q in queues]
    result = client.blpop(queue_keys, timeout=timeout)
    if not result:
        return None

    _queue_key, task_json = result
    try:
        return json.loads(task_json)
    except Exception as e:
        logger.error("Failed to parse task JSON: %s (payload: %s)", e, task_json)
        return None


def execute_task(task_payload):
    """Execute a task payload by importing and calling the target callable."""
    func_path = task_payload["func"]
    fn = _TASK_REGISTRY.get(func_path)
    if fn is None:
        module_name, func_name = func_path.rsplit(".", 1)
        mod = importlib.import_module(module_name)
        fn = getattr(mod, func_name)

    return fn(*task_payload.get("args", []), **task_payload.get("kwargs", {}))


def mark_failed(task_payload, exc):
    """Handle task failure: retry with exponential backoff or send to Dead Letter Queue."""
    task_payload["retries"] = task_payload.get("retries", 0) + 1
    task_payload["last_error"] = str(exc)
    task_payload["failed_at"] = time.time()

    client = get_redis_client()
    if not client:
        return

    q = task_payload.get("queue", "default")
    if task_payload["retries"] <= task_payload.get("max_retries", 3):
        backoff = 2 ** task_payload["retries"]
        task_payload["eta"] = time.time() + backoff
        serialized = json.dumps(task_payload, cls=QueueJSONEncoder)
        client.zadd(f"queue:delayed:{q}", {serialized: task_payload["eta"]})
        logger.warning(
            "Task %s failed (attempt %d/%d). Retrying in %ds: %s",
            task_payload["id"],
            task_payload["retries"],
            task_payload["max_retries"],
            backoff,
            exc,
        )
    else:
        serialized = json.dumps(task_payload, cls=QueueJSONEncoder)
        client.rpush("queue:dead_letter", serialized)
        logger.error("Task %s exceeded max retries. Moved to dead_letter queue: %s", task_payload["id"], exc)


def get_queue_stats():
    """Return task counts across all queues."""
    client = get_redis_client()
    if not client:
        return {}
    queues = ["default", "ai", "notifications", "webhooks", "scheduled", "dead_letter"]
    stats = {}
    for q in queues:
        length = client.llen(f"queue:{q}")
        delayed = client.zcard(f"queue:delayed:{q}")
        stats[q] = {"length": length, "delayed": delayed}
    return stats
