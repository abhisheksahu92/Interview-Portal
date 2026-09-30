"""Dedicated background worker process for Render.

Listens on Redis/Valkey queues (AI, notifications, webhooks, scheduled, default),
handles graceful shutdown on SIGTERM/SIGINT, refreshes database connections,
and routes task failures to exponential backoff / Dead Letter Queue.
"""

import logging
import signal
import sys
import time

from django import db
from django.core.management.base import BaseCommand

from core.queue import dequeue, execute_task, mark_failed

logger = logging.getLogger("core.worker")


class Command(BaseCommand):
    help = "Run the dedicated background worker process for AI, notifications, and queues."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shutdown_requested = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--queues",
            type=str,
            default="ai,notifications,webhooks,scheduled,default",
            help="Comma-separated queue priority list (default: ai,notifications,webhooks,scheduled,default)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=2,
            help="Polling timeout in seconds (default: 2)",
        )
        parser.add_argument(
            "--burst",
            action="store_true",
            help="Run until all queues are empty, then exit (useful for testing and batch processing).",
        )

    def handle(self, *args, **options):
        queue_names = [q.strip() for q in options["queues"].split(",") if q.strip()]
        timeout = options["timeout"]
        burst = options["burst"]

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting background worker on queues: {', '.join(queue_names)} (PID {sys.argv[0]})"
            )
        )

        tasks_processed = 0

        while not self.shutdown_requested:
            # Clean up old/idle database connections before waiting
            db.close_old_connections()

            task = dequeue(queues=queue_names, timeout=timeout)
            if task is None:
                if burst:
                    self.stdout.write("Burst mode: all queues empty, exiting.")
                    break
                continue

            task_id = task.get("id", "unknown")
            func_name = task.get("func", "unknown")
            q = task.get("queue", "default")
            start = time.time()

            logger.info("Starting task %s: %s [queue=%s]", task_id, func_name, q)

            try:
                result = execute_task(task)
                duration = time.time() - start
                tasks_processed += 1
                logger.info("Completed task %s in %.2fs", task_id, duration)
                self.stdout.write(
                    self.style.SUCCESS(f"  OK   {func_name} ({task_id}) in {duration:.2f}s")
                )
            except Exception as exc:
                duration = time.time() - start
                logger.exception("Task %s failed in %.2fs: %s", task_id, duration, exc)
                self.stdout.write(
                    self.style.ERROR(f"  FAIL {func_name} ({task_id}) in {duration:.2f}s: {exc}")
                )
                try:
                    mark_failed(task, exc)
                except Exception as dlq_err:
                    logger.error("Failed to mark task failed in queue: %s", dlq_err)
            finally:
                db.close_old_connections()

        self.stdout.write(self.style.SUCCESS(f"Worker shutdown gracefully. Total tasks processed: {tasks_processed}"))

    def _handle_signal(self, signum, frame):
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        self.stdout.write(self.style.WARNING(f"Received {sig_name}. Finishing current task and stopping..."))
        self.shutdown_requested = True
