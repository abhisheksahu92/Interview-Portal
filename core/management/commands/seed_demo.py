from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Company, Membership, User

DEMO_PASSWORD = "demo1234"

DEMO_TEAM = [
    ("owner@demo.test", "Dana", "Owner", Membership.OWNER),
    ("recruiter@demo.test", "Riley", "Recruiter", Membership.RECRUITER),
    ("interviewer@demo.test", "Ira", "Interviewer", Membership.INTERVIEWER),
]

DEMO_CANDIDATE = ("candidate@demo.test", "Cam", "Candidate")


class Command(BaseCommand):
    help = "Create a demo company with owner, recruiter, interviewer and candidate users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company",
            default="Demo Staffing",
            help="Name of the demo company (default: Demo Staffing).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        name = options["company"]
        company = Company.objects.filter(name=name).first()
        created = company is None
        if created:
            company = Company.objects.create(name=name, slug=Company.unique_slug(name))
        self.stdout.write(
            f"{'Created' if created else 'Reusing'} company: {company.name} ({company.slug})"
        )

        for email, first, last, role in DEMO_TEAM:
            user = self._upsert_user(email, first, last, is_candidate=False)
            Membership.objects.get_or_create(
                user=user, company=company, defaults={"role": role}
            )
            self.stdout.write(f"  {role:<12} {email}")

        email, first, last = DEMO_CANDIDATE
        self._upsert_user(email, first, last, is_candidate=True)
        self.stdout.write(f"  {'CANDIDATE':<12} {email}")

        self.stdout.write(
            self.style.SUCCESS(f"Demo data ready. Password for all users: {DEMO_PASSWORD}")
        )

    def _upsert_user(self, email, first_name, last_name, *, is_candidate):
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "is_candidate": is_candidate,
            },
        )
        user.first_name = first_name
        user.last_name = last_name
        user.is_candidate = is_candidate
        user.set_password(DEMO_PASSWORD)
        user.save()
        return user
