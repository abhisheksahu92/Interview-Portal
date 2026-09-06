"""Fetch every enabled source and retire stale leads.

``manage.py fetch_sources [--only <slug> ...]``

Wired into ``PERIODIC_COMMANDS`` so the lead pool refreshes on its own. Each
source is isolated: one broken feed records its error and the rest still run.
"""

from django.core.management.base import BaseCommand

from sources import services
from sources.models import Source


class Command(BaseCommand):
    help = "Fetch opportunity leads from every enabled source."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only", action="append", metavar="SLUG", help="Run only this source (repeatable)."
        )
        parser.add_argument(
            "--no-llm",
            action="store_true",
            help="Tag skills by keyword only (fast; use for a first bulk import).",
        )

    def handle(self, *args, **options):
        only = options.get("only") or []
        unknown = sorted(
            set(only) - set(Source.objects.filter(slug__in=only).values_list("slug", flat=True))
        )
        if unknown:
            self.stderr.write(f"No source with slug {', '.join(map(repr, unknown))}.")
            return None
        rows = services.run_all(only=only, use_llm=not options.get("no_llm"))
        for stats in rows:
            self.stdout.write(
                f"{stats['source']}: {stats['status']} "
                f"seen={stats['seen']} new={stats['created']}"
            )
        expired = services.expire_stale()
        total = sum(row["created"] for row in rows)
        self.stdout.write(
            self.style.SUCCESS(f"{len(rows)} source(s), {total} new lead(s), {expired} expired.")
        )
        return None
