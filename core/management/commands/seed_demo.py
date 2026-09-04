"""Create a fully populated demo company: team, skills, jobs, questions,
an assessment, candidates with applications spread across the pipeline, and a
review — plus one of every Phase 3 paid artefact (end client + portal link,
client submission, interviewer availability, a confirmed interview, a small
talent pool, an offer out for signature, a published careers site and a video
screen) so every screen in the product has something real to show.

Idempotent -- re-running only tops up what is missing. The three shareable
tokens (client portal, candidate booking, offer signing) are printed at the end
for manual testing.
"""

from datetime import time, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from billing.models import Subscription
from billing.services import agency_plan, set_plan
from core.models import Company, Membership, User

DEMO_PASSWORD = "demo1234"

DEMO_TEAM = [
    ("owner@demo.test", "Dana", "Owner", Membership.OWNER),
    ("recruiter@demo.test", "Riley", "Recruiter", Membership.RECRUITER),
    ("interviewer@demo.test", "Ira", "Interviewer", Membership.INTERVIEWER),
]

DEMO_CANDIDATE = ("candidate@demo.test", "Cam", "Candidate")

DEMO_SKILLS = ["Python", "Django", "React"]

DEMO_TIMEZONE = "Asia/Kolkata"

# (email, name, headline, experience_years, skills) -- sourced, not applicants.
DEMO_TALENT = [
    ("divya@talent.test", "Divya Nair", "Senior Python engineer", 7, ["Python", "Django"]),
    ("farid@talent.test", "Farid Khan", "React / TypeScript lead", 6, ["React"]),
    ("gita@talent.test", "Gita Bose", "Full-stack (Django + React)", 4, ["Django", "React"]),
]

DEMO_JOBS = [
    {
        "title": "Senior Django Developer",
        "location": "Pune, IN",
        "description": "Build and scale multi-tenant Django services for our clients.",
        "requirements": "5+ years Python, strong Django ORM/DRF, PostgreSQL.",
        "skills": ["Python", "Django"],
    },
    {
        "title": "Frontend Engineer (React)",
        "location": "Remote",
        "description": "Own the client-facing React app and its design system.",
        "requirements": "3+ years React, TypeScript, accessible component work.",
        "skills": ["React"],
    },
]

DEMO_QUESTIONS = [
    {
        "kind": "MCQ",
        "text": "Which Django ORM call avoids the N+1 query problem for a ForeignKey?",
        "options": ["values()", "select_related()", "only()", "iterator()"],
        "correct_option": 1,
        "difficulty": "EASY",
        "skill": "Django",
    },
    {
        "kind": "MCQ",
        "text": "In Python, what does a list comprehension return?",
        "options": ["A generator", "A tuple", "A new list", "None"],
        "correct_option": 2,
        "difficulty": "EASY",
        "skill": "Python",
    },
    {
        "kind": "TEXT",
        "text": "Describe how you would design a multi-tenant data model in Django.",
        "options": [],
        "correct_option": None,
        "difficulty": "HARD",
        "skill": "Django",
    },
]

# (email, first, last, headline, experience_years, stage index into job.stages)
DEMO_APPLICANTS = [
    ("asha@demo.test", "Asha", "Rao", "Django engineer, 6 yrs", 6, 0),
    ("ben@demo.test", "Ben", "Ortiz", "Full-stack Python dev", 4, 1),
    ("chen@demo.test", "Chen", "Li", "Backend engineer", 8, 3),
]


class Command(BaseCommand):
    help = "Seed a demo company with team, skills, jobs, questions, applications."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company",
            default="Demo Staffing",
            help="Name of the demo company (default: Demo Staffing).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        # Imported here so the command stays importable before migrations run.
        from assessments.models import Assessment, Question
        from jobs.models import (
            Application,
            CandidateProfile,
            Job,
            PipelineStage,
            Skill,
            StageReview,
        )

        name = options["company"]
        company = Company.objects.filter(name=name).first()
        created = company is None
        if created:
            company = Company.objects.create(name=name, slug=Company.unique_slug(name))
        self.stdout.write(
            f"{'Created' if created else 'Reusing'} company: {company.name} ({company.slug})"
        )

        # --- billing ------------------------------------------------------
        # The demo seeds more than one OPEN job, which the FREE plan forbids
        # (billing enforces the limit via a pre_save signal on Job), and every
        # Phase 3 feature below is entitlement-gated. So put the demo company on
        # a genuinely paid AGENCY plan -- not a trial, whose expiry would quietly
        # turn the demo back into a FREE tenant -- before any job is created.
        plan = agency_plan()
        subscription = Subscription.objects.filter(company=company).first()
        if subscription is None:
            subscription = Subscription.objects.create(
                company=company,
                plan=plan,
                status=Subscription.ACTIVE,
                trial_ends_at=None,
            )
        elif (
            subscription.plan_id != plan.pk
            or not subscription.is_usable
            or subscription.trial_ends_at is not None
        ):
            set_plan(
                subscription, plan, status=Subscription.ACTIVE, trial_ends_at=None
            )
        self.stdout.write(f"  plan: {subscription.plan.name} (paid, not trialing)")

        # --- team ---------------------------------------------------------
        team = {}
        for email, first, last, role in DEMO_TEAM:
            user = self._upsert_user(email, first, last, is_candidate=False)
            Membership.objects.get_or_create(
                user=user, company=company, defaults={"role": role}
            )
            team[role] = user
            self.stdout.write(f"  {role:<12} {email}")

        email, first, last = DEMO_CANDIDATE
        demo_candidate = self._upsert_user(email, first, last, is_candidate=True)
        CandidateProfile.objects.get_or_create(
            user=demo_candidate, defaults={"experience_years": 3}
        )
        self.stdout.write(f"  {'CANDIDATE':<12} {email}")

        # --- skills -------------------------------------------------------
        skills = {}
        for skill_name in DEMO_SKILLS:
            skill, _ = Skill.objects.get_or_create(company=company, name=skill_name)
            skills[skill_name] = skill
        self.stdout.write(f"  skills: {', '.join(skills)}")

        # --- jobs (Job.save() seeds the default pipeline) -----------------
        jobs = []
        for spec in DEMO_JOBS:
            job, job_created = Job.objects.get_or_create(
                company=company,
                title=spec["title"],
                defaults={
                    "location": spec["location"],
                    "description": spec["description"],
                    "requirements": spec["requirements"],
                    "status": Job.OPEN,
                    "created_by": team.get(Membership.RECRUITER),
                },
            )
            if not job_created and job.status != Job.OPEN:
                job.status = Job.OPEN
                job.save(update_fields=["status"])
            job.skills.set([skills[s] for s in spec["skills"]])
            jobs.append(job)
            self.stdout.write(
                f"  job: {job.title} ({job.stages.count()} stages)"
                f"{' [new]' if job_created else ''}"
            )

        # --- question bank + one assessment on job 1's Assessment stage ---
        questions = []
        for spec in DEMO_QUESTIONS:
            question, _ = Question.objects.get_or_create(
                company=company,
                text=spec["text"],
                defaults={
                    "kind": spec["kind"],
                    "options": spec["options"],
                    "correct_option": spec["correct_option"],
                    "difficulty": spec["difficulty"],
                    "skill": skills.get(spec["skill"]),
                    "source": Question.MANUAL,
                },
            )
            questions.append(question)

        assessment_stage = jobs[0].stages.filter(kind=PipelineStage.ASSESSMENT).first()
        if assessment_stage is not None:
            assessment, _ = Assessment.objects.get_or_create(
                job=jobs[0],
                stage=assessment_stage,
                title=f"{jobs[0].title} screening test",
                defaults={"time_limit_minutes": 30, "pass_mark_percent": 60},
            )
            assessment.questions.set(questions)
            self.stdout.write(
                f"  assessment: {assessment.title} ({assessment.questions.count()} questions)"
            )

        # --- candidates + applications across stages ----------------------
        stages = list(jobs[0].stages.all())
        applications = []
        for email, first, last, headline, years, stage_index in DEMO_APPLICANTS:
            user = self._upsert_user(email, first, last, is_candidate=True)
            profile, _ = CandidateProfile.objects.get_or_create(
                user=user,
                defaults={
                    "headline": headline,
                    "experience_years": years,
                    "notice_period_days": 30,
                },
            )
            profile.skills.set(list(skills.values())[:2])
            stage = stages[stage_index] if stage_index < len(stages) else jobs[0].first_stage
            application, _ = Application.objects.get_or_create(
                job=jobs[0],
                candidate=profile,
                defaults={"current_stage": stage, "ai_fit_score": 60 + years * 4},
            )
            applications.append(application)
            self.stdout.write(
                f"  applicant: {email} -> {application.current_stage.name if application.current_stage else '—'}"
            )

        # --- one interviewer review --------------------------------------
        reviewed = applications[-1]
        if reviewed.current_stage is not None:
            StageReview.objects.get_or_create(
                application=reviewed,
                stage=reviewed.current_stage,
                reviewer=team[Membership.INTERVIEWER],
                defaults={
                    "decision": StageReview.HOLD,
                    "rating": 4,
                    "feedback": "Strong backend fundamentals; waiting on the client slot.",
                },
            )
            self.stdout.write(f"  review: {reviewed.candidate.user.email} (HOLD)")

        # --- Phase 3 paid artefacts ---------------------------------------
        tokens = {}
        tokens.update(self._seed_client(company, applications[0], team))
        self._seed_availability(company, team[Membership.INTERVIEWER])
        tokens.update(self._seed_interview(company, applications, stages, team))
        self._seed_talent(company, skills)
        tokens.update(self._seed_offer(company, applications[-1], team))
        self._seed_careers(company)
        self._seed_video(company, jobs[1])

        # Analytics reads StageTransition history; the applications above were
        # created directly, so give them their synthetic first transition.
        call_command("backfill_stage_transitions", company=company.slug, verbosity=0)
        self.stdout.write("  analytics: stage transitions backfilled")

        self.stdout.write(
            self.style.SUCCESS(f"Demo data ready. Password for all users: {DEMO_PASSWORD}")
        )
        self.stdout.write("Shareable tokens (no login needed):")
        for label, path in sorted(tokens.items()):
            self.stdout.write(f"  {label:<14} {path}")

    # --- Phase 3 seeders --------------------------------------------------

    def _seed_client(self, company, application, team):
        """An end client, a live portal link, and one candidate submitted to it."""
        from clients.models import Client, ClientAccess, Submission

        client, _ = Client.objects.get_or_create(
            company=company,
            name="Northwind Retail",
            defaults={
                "contact_name": "Nina Wells",
                "contact_email": "nina@northwind.test",
                "notes": "Long-running Django staffing account.",
            },
        )
        access = client.accesses.filter(email="nina@northwind.test").first()
        if access is None:
            access = ClientAccess.objects.create(
                client=client,
                email="nina@northwind.test",
                expires_at=timezone.now()
                + timedelta(days=ClientAccess.DEFAULT_VALID_DAYS),
            )
        elif not access.is_active:
            access.rotate()
        submission, created = Submission.objects.get_or_create(
            application=application,
            client=client,
            defaults={
                "submitted_by": team.get(Membership.RECRUITER),
                "note": "Strong Django match — available at 30 days notice.",
            },
        )
        self.stdout.write(
            f"  client: {client.name} (1 portal link, submission "
            f"{'created' if created else 'reused'} for {submission.candidate.user.email})"
        )
        return {"client portal": reverse("clients:portal", args=[access.token])}

    def _seed_availability(self, company, interviewer):
        """Mon-Fri 10:00-17:00 IST for the demo interviewer."""
        from scheduling.models import InterviewerAvailability

        created = 0
        for weekday in range(5):  # Monday..Friday
            _, made = InterviewerAvailability.objects.get_or_create(
                company=company,
                user=interviewer,
                weekday=weekday,
                start=time(10, 0),
                end=time(17, 0),
                defaults={"timezone": DEMO_TIMEZONE},
            )
            created += 1 if made else 0
        self.stdout.write(
            f"  availability: {interviewer.email} Mon-Fri 10:00-17:00 {DEMO_TIMEZONE}"
            f" ({created} new)"
        )

    def _seed_interview(self, company, applications, stages, team):
        """One confirmed interview on the L2 stage, for the booking page."""
        from scheduling.models import Interview

        l2_stage = next(
            (s for s in stages if s.name.startswith("L2")),
            None,
        )
        application = next(
            (a for a in applications if a.current_stage_id == getattr(l2_stage, "pk", None)),
            applications[-1],
        )
        interview = (
            Interview.objects.filter(application=application)
            .order_by("scheduled_start", "pk")
            .first()
        )
        if interview is None:
            start = (timezone.now() + timedelta(days=2)).replace(
                minute=0, second=0, microsecond=0
            )
            interview = Interview.objects.create(
                company=company,
                application=application,
                stage=l2_stage,
                scheduled_start=start,
                scheduled_end=start + timedelta(minutes=60),
                timezone=DEMO_TIMEZONE,
                location_or_link="https://meet.example.test/demo-l2",
                status=Interview.CONFIRMED,
                created_by=team.get(Membership.RECRUITER),
                notes="System design deep dive.",
            )
            interview.interviewers.set([team[Membership.INTERVIEWER]])
        self.stdout.write(
            f"  interview: {application.candidate.user.email} "
            f"{interview.scheduled_start:%Y-%m-%d %H:%M} [{interview.status}]"
        )
        return {"booking": reverse("scheduling:book", args=[interview.booking_token])}

    def _seed_talent(self, company, skills):
        """A small sourced talent pool so the talent search has results."""
        from talent.models import TalentProfile

        for email, name, headline, years, skill_names in DEMO_TALENT:
            profile, _ = TalentProfile.objects.get_or_create(
                company=company,
                email=email,
                defaults={
                    "name": name,
                    "headline": headline,
                    "experience_years": years,
                    "location": "Pune, IN",
                    "source": TalentProfile.MANUAL,
                    "resume_text": f"{name} — {headline}. Skills: {', '.join(skill_names)}.",
                },
            )
            profile.skills.set([skills[s] for s in skill_names if s in skills])
        self.stdout.write(f"  talent: {len(DEMO_TALENT)} sourced profiles")

    def _seed_offer(self, company, application, team):
        """A default offer template plus one offer already out for signature."""
        from offers.models import Offer, OfferTemplate
        from offers.services import render_offer

        template = OfferTemplate.default_for(company)
        offer = Offer.objects.filter(application=application).order_by("pk").first()
        if offer is None:
            offer = Offer.objects.create(
                application=application,
                template=template,
                salary=Decimal("2400000"),
                currency="INR",
                joining_date=(timezone.now() + timedelta(days=30)).date(),
                expires_at=timezone.now() + timedelta(days=10),
                created_by=team.get(Membership.OWNER),
            )
        if offer.status == Offer.DRAFT:
            # Marked SENT directly rather than through offers.services.send_offer:
            # seeding must never touch email or the PDF gateway.
            render_offer(offer, save=True)
            offer.status = Offer.SENT
            offer.sent_at = timezone.now()
            offer.save(update_fields=["status", "sent_at", "updated_at"])
        self.stdout.write(
            f"  offer: {application.candidate.user.email} [{offer.status}] "
            f"via template “{template.name}”"
        )
        return {"offer sign": reverse("offers:sign", args=[offer.sign_token])}

    def _seed_careers(self, company):
        """A published careers site so the public page and Indeed feed work."""
        from careers.models import CareersSite

        site, _ = CareersSite.objects.get_or_create(
            company=company,
            defaults={
                "slug": company.slug,
                "headline": f"Build with {company.name}",
                "about": "We staff and run product engineering teams for growing companies.",
                "published": True,
            },
        )
        if not site.published:
            site.published = True
            site.save(update_fields=["published"])
        self.stdout.write(f"  careers: /careers/{site.slug}/ (published)")

    def _seed_video(self, company, job):
        """One video question and an active screen on the job's Screening stage."""
        from jobs.models import PipelineStage
        from video.models import VideoQuestion, VideoScreen

        question, _ = VideoQuestion.objects.get_or_create(
            company=company,
            text="Walk us through a React component you are proud of and why.",
            defaults={"think_seconds": 30, "answer_seconds": 120},
        )
        stage = job.stages.filter(kind=PipelineStage.SCREENING).first()
        screen, created = VideoScreen.objects.get_or_create(
            job=job,
            title=f"{job.title} video screen",
            defaults={"stage": stage, "deadline_days": 5, "is_active": True},
        )
        if not created and not screen.is_active:
            screen.is_active = True
            screen.save(update_fields=["is_active"])
        screen.questions.set([question])
        self.stdout.write(
            f"  video: “{screen.title}” on {stage.name if stage else '—'} "
            f"({screen.questions.count()} question)"
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
