"""Issue a signed self-hosted licence key for a company."""

from django.core.management.base import BaseCommand, CommandError

from core.models import Company
from partners.licensing import LicenseSigningUnavailable, issue_license


class Command(BaseCommand):
    help = "Issue a self-hosted licence key: --company <slug|id> --seats N --days N"

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True, help="Company slug or id")
        parser.add_argument("--seats", type=int, default=5)
        parser.add_argument("--days", type=int, default=365)

    def handle(self, *args, **options):
        ident = options["company"]
        company = Company.objects.filter(slug=ident).first()
        if company is None and str(ident).isdigit():
            company = Company.objects.filter(pk=int(ident)).first()
        if company is None:
            raise CommandError(f"No company matching {ident!r}.")
        try:
            licence = issue_license(company, seats=options["seats"], days=options["days"])
        except LicenseSigningUnavailable as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Issued licence for {company.name}: {licence.seats} seats, "
                f"expires {licence.expires_at:%Y-%m-%d}"
            )
        )
        self.stdout.write(licence.key)
        return licence.key
