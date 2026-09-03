"""Re-run AI fit scoring over existing applications.

Useful after an ``ANTHROPIC_API_KEY`` is configured, or after the fit prompt
changes: applications created while AI was disabled keep no score, and this
backfills them.
"""

from django.core.management.base import BaseCommand, CommandError

from jobs.models import Application


class Command(BaseCommand):
    help = "Re-run AI fit scoring (summarize_fit) for existing applications."

    def add_arguments(self, parser):
        parser.add_argument("--company", help="Company slug to limit scoring to.")
        parser.add_argument("--job", type=int, help="Job id to limit scoring to.")
        parser.add_argument("--all", action="store_true", help="Score every application.")
        parser.add_argument(
            "--missing-only",
            action="store_true",
            help="Only score applications that have no fit score yet.",
        )

    def handle(self, *args, **options):
        from assessments import ai

        if not any([options.get("company"), options.get("job"), options.get("all")]):
            raise CommandError("Pass one of --company <slug>, --job <id> or --all.")

        queryset = Application.objects.select_related("job", "candidate").order_by("pk")
        if options.get("company"):
            queryset = queryset.filter(job__company__slug=options["company"])
        if options.get("job"):
            queryset = queryset.filter(job_id=options["job"])
        if options.get("missing_only"):
            queryset = queryset.filter(ai_fit_score__isnull=True)

        total = queryset.count()
        if not total:
            self.stdout.write("No matching applications.")
            return

        scored = failed = 0
        for application in queryset.iterator():
            try:
                score = ai.summarize_fit(application)
            except Exception as exc:  # pragma: no cover - AI is best-effort
                score = None
                self.stderr.write(f"application {application.pk}: {exc}")
            if score is None:
                failed += 1
            else:
                scored += 1
                self.stdout.write(f"application {application.pk}: {score}")

        self.stdout.write(
            self.style.SUCCESS(f"Scored {scored}/{total} applications ({failed} skipped).")
        )
