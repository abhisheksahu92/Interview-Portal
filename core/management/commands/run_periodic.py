"""Run every scheduled maintenance job, in order, in one process.

One cron entry (or one Fly/Railway scheduled task) can call this instead of
eight; a job that raises is logged and the rest still run, because a broken
dunning run must not stop interview reminders going out.

    */15 * * * * cd /app && python manage.py run_periodic
"""

import logging
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

#: Commands to run, in dependency order: subscription state first (trials and
#: dunning decide what a company is entitled to), then the per-app sweeps, then
#: the money that follows from them.
PERIODIC_COMMANDS = [
    "expire_trials",
    "run_dunning",
    "send_interview_reminders",
    "expire_offers",
    "retry_failed",
    "process_video_responses",
    "compute_commissions",
    "expire_video_invites",
    "deliver_webhooks",
]


def available_commands():
    """The subset of :data:`PERIODIC_COMMANDS` this install actually ships."""
    from django.core.management import get_commands

    known = get_commands()
    return [name for name in PERIODIC_COMMANDS if name in known]


class Command(BaseCommand):
    help = "Run all periodic maintenance commands in order, logging failures."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            action="append",
            default=None,
            metavar="COMMAND",
            help="Run only this periodic command (repeatable).",
        )
        parser.add_argument(
            "--skip",
            action="append",
            default=None,
            metavar="COMMAND",
            help="Skip this periodic command (repeatable).",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="Print the commands that would run and exit.",
        )

    def handle(self, *args, **options):
        names = available_commands()
        if options.get("only"):
            wanted = set(options["only"])
            names = [name for name in names if name in wanted]
        if options.get("skip"):
            names = [name for name in names if name not in set(options["skip"])]

        if options.get("list"):
            for name in names:
                self.stdout.write(name)
            return

        failures = []
        for name in names:
            started = time.monotonic()
            try:
                call_command(name)
            except Exception as exc:  # one broken job must not stop the rest
                failures.append(name)
                logger.exception("run_periodic: %s failed: %s", name, exc)
                self.stderr.write(self.style.ERROR(f"{name}: FAILED ({exc})"))
            else:
                elapsed = time.monotonic() - started
                self.stdout.write(f"{name}: ok ({elapsed:.2f}s)")

        summary = f"Ran {len(names)} periodic command(s), {len(failures)} failed."
        if failures:
            self.stderr.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
