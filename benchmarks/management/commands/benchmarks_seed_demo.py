"""Seed enough accepted offers for the benchmark report to have real cells.

``manage.py benchmarks_seed_demo [--company "Demo Staffing"] [--partner "Benchmark Partner"]``

The report suppresses any cell computed from fewer than ``metrics.MIN_N``
offers, so a fresh demo database shows nothing but "hidden" rows. This command
creates ~40 accepted offers across three skills and two cities, split over two
companies, which is enough for every skill cell to clear the threshold *and*
for the "your offers vs market" panel to show a real gap.

It is deliberately a separate command rather than an extension of
``core.seed_demo`` (that app belongs to another agent) and is idempotent: it
tops each cohort up to its target size instead of appending on every run.
"""

import datetime as dt
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# (skill, city, base annual pay, spread between offers)
COHORTS = [
    ("Python", "Pune", Decimal("1400000"), Decimal("60000")),
    ("Python", "Bengaluru", Decimal("1700000"), Decimal("70000")),
    ("React", "Pune", Decimal("1200000"), Decimal("50000")),
    ("React", "Bengaluru", Decimal("1500000"), Decimal("55000")),
    ("QA Automation", "Pune", Decimal("900000"), Decimal("40000")),
    ("QA Automation", "Bengaluru", Decimal("1050000"), Decimal("45000")),
]
#: Offers per cohort per company — 6 cohorts x 2 companies x 4 = 48 offers.
PER_COHORT = 4
EXPERIENCE_BY_INDEX = (Decimal("2.0"), Decimal("4.0"), Decimal("7.0"), Decimal("11.0"))


class Command(BaseCommand):
    help = "Create accepted offers so the salary benchmarks have publishable cells."

    def add_arguments(self, parser):
        parser.add_argument("--company", default="Demo Staffing", help="Primary demo company.")
        parser.add_argument(
            "--partner",
            default="Benchmark Partner",
            help="Second company, so market cells are not one tenant's data.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from core.models import Company

        total = 0
        for name in (options["company"], options["partner"]):
            company = Company.objects.filter(name=name).first()
            if company is None:
                company = Company.objects.create(name=name, slug=Company.unique_slug(name))
                self.stdout.write(f"Created company: {company.name}")
            total += self._seed_company(company)
        self.stdout.write(self.style.SUCCESS(f"{total} accepted offer(s) now on file."))
        return None

    def _seed_company(self, company):
        from jobs.models import Application, CandidateProfile, Job, Skill
        from offers.models import Offer

        User = _user_model()
        made = 0
        for skill_name, city, base, step in COHORTS:
            skill, _ = Skill.objects.get_or_create(company=company, name=skill_name)
            title = f"{skill_name} Engineer — {city}"
            job = Job.objects.filter(company=company, title=title).first()
            if job is None:
                job = Job.objects.create(
                    company=company,
                    title=title,
                    location=f"{city}, India",
                    status=Job.CLOSED,
                    salary_period=Job.YEAR,
                )
            job.skills.add(skill)
            existing = Offer.objects.filter(
                application__job=job, status=Offer.ACCEPTED
            ).count()
            for index in range(existing, PER_COHORT):
                email = f"bench-{company.pk}-{skill_name.lower().replace(' ', '')}-{city.lower()}-{index}@example.test"
                user = User.objects.filter(email=email).first() or User.objects.create_user(
                    email=email, password="benchmark-demo-only"
                )
                profile, _ = CandidateProfile.objects.get_or_create(
                    user=user,
                    defaults={"experience_years": EXPERIENCE_BY_INDEX[index % 4]},
                )
                application, _ = Application.objects.get_or_create(
                    job=job, candidate=profile
                )
                Offer.objects.create(
                    application=application,
                    salary=base + step * index,
                    currency="INR",
                    status=Offer.ACCEPTED,
                    joining_date=timezone.localdate() + dt.timedelta(days=30),
                    signed_name=email,
                    signed_at=timezone.now() - dt.timedelta(days=30 + index * 7),
                )
                made += 1
        if made:
            self.stdout.write(f"{company.name}: {made} accepted offer(s) added")
        return Offer.objects.filter(application__job__company=company, status=Offer.ACCEPTED).count()


def _user_model():
    from django.contrib.auth import get_user_model

    return get_user_model()
