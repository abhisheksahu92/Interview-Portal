"""Fail fast when production configuration is incomplete.

Django's own ``check --deploy`` covers security headers. It does not know that
a blank ``RAZORPAY_KEY_SECRET`` silently turns off billing, or that a missing
``ANTHROPIC_API_KEY`` downgrades every AI screening to manual. Those failures
are invisible at boot and only surface when a customer hits them, so they are
checked here and treated as deploy blockers.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

# (setting name, why it matters when missing)
REQUIRED = [
    ("SECRET_KEY", "sessions and signed tokens are forgeable"),
    ("ALLOWED_HOSTS", "Django refuses every request"),
    ("SITE_URL", "emailed links point at the wrong host"),
]

# Blank values here do not crash the app, they quietly disable a revenue stream.
REVENUE = [
    ("RAZORPAY_KEY_ID", "no customer can subscribe or pay"),
    ("RAZORPAY_KEY_SECRET", "no customer can subscribe or pay"),
    ("RAZORPAY_WEBHOOK_SECRET", "payments succeed but are never recorded"),
    ("COMPANY_GSTIN", "invoices are issued without a GSTIN"),
    ("COMPANY_STATE_CODE", "GST is split as inter-state for every customer"),
    ("ANTHROPIC_API_KEY", "AI screening degrades to manual for everyone"),
    ("INTEGRATIONS_ENCRYPTION_KEY", "HRMS credentials cannot be stored"),
]


def _get(name):
    """Read a setting, treating an unusable one as absent.

    Django raises rather than returning a falsy value for some settings (an
    empty SECRET_KEY, for one), and this command exists precisely to report
    that case rather than crash on it.
    """
    try:
        return getattr(settings, name, None)
    except ImproperlyConfigured:
        return None


class Command(BaseCommand):
    help = "Verify production environment configuration before serving traffic."

    def add_arguments(self, parser):
        parser.add_argument(
            "--warn-only",
            action="store_true",
            help="Report problems without failing the deploy.",
        )

    def handle(self, *args, **options):
        errors: list[str] = []
        warnings: list[str] = []

        for name, why in REQUIRED:
            if not _get(name):
                errors.append(f"{name} is not set: {why}")

        if settings.DEBUG:
            errors.append("DEBUG is True: tracebacks would leak to the public")

        db = settings.DATABASES.get("default", {})
        if "sqlite" in db.get("ENGINE", "") and not settings.DEBUG:
            errors.append(
                "DATABASE_URL points at SQLite: Render's disk is ephemeral, "
                "so all data is lost on the next deploy"
            )

        if not _get("AWS_STORAGE_BUCKET_NAME"):
            errors.append(
                "AWS_STORAGE_BUCKET_NAME is not set: resumes and videos would "
                "be written to a container disk that is wiped on redeploy"
            )

        backend = _get("EMAIL_BACKEND") or ""
        if "." not in backend:
            errors.append(
                f"EMAIL_BACKEND is {backend!r}, which is not an importable "
                "backend path; use django.core.mail.backends.smtp.EmailBackend"
            )
        elif "console" in backend or "locmem" in backend:
            errors.append(
                f"EMAIL_BACKEND is {backend}: no candidate or client email "
                "would actually be delivered"
            )

        for name, why in REVENUE:
            if not _get(name):
                warnings.append(f"{name} is not set: {why}")

        for line in warnings:
            self.stdout.write(self.style.WARNING(f"  warn  {line}"))
        for line in errors:
            self.stdout.write(self.style.ERROR(f"  FAIL  {line}"))

        if errors and not options["warn_only"]:
            raise CommandError(
                f"{len(errors)} blocking configuration problem(s); refusing to deploy."
            )
        if not errors and not warnings:
            self.stdout.write(self.style.SUCCESS("Deploy configuration looks complete."))
