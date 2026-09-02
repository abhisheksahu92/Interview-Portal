"""Create a fully populated demo company: team, skills, jobs, questions,
an assessment, candidates with applications spread across the pipeline, and a
review. Idempotent -- re-running only tops up what is missing.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from billing.models import Subscription
from billing.services import pro_plan, set_plan
from core.models import Company, Membership, User

DEMO_PASSWORD = "demo1234"

DEMO_TEAM = [
    ("owner@demo.test", "Dana", "Owner", Membership.OWNER),
    ("recruiter@demo.test", "Riley", "Recruiter", Membership.RECRUITER),
    ("interviewer@demo.test", "Ira", "Interviewer", Membership.INTERVIEWER),
]

DEMO_CANDIDATE = ("candidate@demo.test", "Cam", "Candidate")

DEMO_SKILLS = ["Python", "Django", "React"]

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
        # (billing enforces the limit via a pre_save signal on Job), so give
        # the demo company a PRO subscription before any job is created.
        plan = pro_plan()
        subscription = Subscription.objects.filter(company=company).first()
        if subscription is None:
            subscription = Subscription.objects.create(
                company=company, plan=plan, status=Subscription.ACTIVE
            )
        elif subscription.plan_id != plan.pk or not subscription.is_usable:
            set_plan(subscription, plan, status=Subscription.ACTIVE)
        self.stdout.write(f"  plan: {subscription.plan.name}")

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
