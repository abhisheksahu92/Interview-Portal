"""Jobs domain models: skills, jobs, pipeline stages, candidates, applications."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from jobs.validators import validate_resume_file


class SkillQuerySet(models.QuerySet):
    def distinct_by_name(self):
        """One Skill per distinct (case-insensitive) name — the lowest pk wins.

        Skills are per-company rows, so a candidate-facing picker would otherwise
        repeat "Python" once per tenant.
        """
        seen, keep = set(), []
        for pk, name in self.order_by("name", "pk").values_list("pk", "name"):
            key = (name or "").strip().casefold()
            if key in seen:
                continue
            seen.add(key)
            keep.append(pk)
        return self.model.objects.filter(pk__in=keep).order_by("name")


class Skill(models.Model):
    """A per-company skill tag (never a hardcoded choice list)."""

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="skills"
    )
    name = models.CharField(max_length=80)

    objects = SkillQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_skill_per_company")
        ]

    def __str__(self):
        return self.name


class Job(models.Model):
    """An open role at a company."""

    FULL_TIME = "FULL_TIME"
    CONTRACT = "CONTRACT"
    INTERN = "INTERN"
    EMPLOYMENT_TYPE_CHOICES = [
        (FULL_TIME, "Full time"),
        (CONTRACT, "Contract"),
        (INTERN, "Intern"),
    ]

    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (OPEN, "Open"),
        (CLOSED, "Closed"),
    ]

    YEAR = "YEAR"
    MONTH = "MONTH"
    SALARY_PERIOD_CHOICES = [
        (YEAR, "per year"),
        (MONTH, "per month"),
    ]
    #: schema.org / Indeed unitText for each period.
    SALARY_UNIT_TEXT = {YEAR: "YEAR", MONTH: "MONTH"}

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="jobs"
    )
    # Optional end client this role is being filled for (clients app / client portal).
    client = models.ForeignKey(
        "clients.Client",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs",
    )
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    requirements = models.TextField(blank=True)
    employment_type = models.CharField(
        max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default=FULL_TIME
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    skills = models.ManyToManyField(Skill, blank=True, related_name="jobs")
    created_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    closes_at = models.DateField(null=True, blank=True)
    # Compensation. Kept optional and hidden by default: a range is only ever
    # published when the recruiter explicitly ticks ``show_salary``.
    salary_min = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    salary_max = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    salary_currency = models.CharField(max_length=8, default="INR", blank=True)
    salary_period = models.CharField(
        max_length=10, choices=SALARY_PERIOD_CHOICES, default=YEAR, blank=True
    )
    show_salary = models.BooleanField(
        default=False,
        help_text="Publish the salary range on the public job and careers pages.",
    )

    DEFAULT_STAGES = [
        ("Screening", "SCREENING", False),
        ("Assessment", "ASSESSMENT", True),
        ("L1 Interview", "INTERVIEW", False),
        ("L2 Interview", "INTERVIEW", False),
        ("HR", "HR", False),
        ("Offer", "OFFER", False),
    ]

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        creating = self._state.adding and not self.pk
        super().save(*args, **kwargs)
        if creating:
            self.seed_default_stages()

    def seed_default_stages(self):
        """Create the default pipeline for a brand new job."""
        if self.stages.exists():
            return
        PipelineStage.objects.bulk_create(
            [
                PipelineStage(
                    job=self,
                    name=name,
                    order=index,
                    kind=kind,
                    requires_assessment=requires_assessment,
                )
                for index, (name, kind, requires_assessment) in enumerate(
                    self.DEFAULT_STAGES, start=1
                )
            ]
        )

    @property
    def first_stage(self):
        return self.stages.order_by("order").first()

    @property
    def is_open(self):
        return self.status == self.OPEN

    @property
    def has_salary(self):
        """True when a range exists at all (regardless of publication)."""
        return self.salary_min is not None or self.salary_max is not None

    @property
    def salary_published(self):
        """True when the range may be shown to the public."""
        return bool(self.show_salary) and self.has_salary

    @property
    def salary_unit_text(self):
        return self.SALARY_UNIT_TEXT.get(self.salary_period, "YEAR")


class PipelineStage(models.Model):
    """One configurable step of a job's hiring pipeline."""

    SCREENING = "SCREENING"
    ASSESSMENT = "ASSESSMENT"
    INTERVIEW = "INTERVIEW"
    HR = "HR"
    OFFER = "OFFER"
    KIND_CHOICES = [
        (SCREENING, "Screening"),
        (ASSESSMENT, "Assessment"),
        (INTERVIEW, "Interview"),
        (HR, "HR"),
        (OFFER, "Offer"),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=80)
    order = models.PositiveIntegerField(default=1)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=INTERVIEW)
    requires_assessment = models.BooleanField(default=False)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["job", "order"], name="uniq_stage_order_per_job")
        ]

    def __str__(self):
        return f"{self.job.title} · {self.name}"

    @property
    def company(self):
        return self.job.company

    def next_stage(self):
        return (
            self.job.stages.filter(order__gt=self.order).order_by("order").first()
        )


class CandidateProfile(models.Model):
    """Extra data for an external applicant."""

    user = models.OneToOneField(
        "core.User", on_delete=models.CASCADE, related_name="candidate_profile"
    )
    phone = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    experience_years = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    notice_period_days = models.PositiveIntegerField(default=0)
    resume = models.FileField(
        upload_to="resumes/", blank=True, validators=[validate_resume_file]
    )
    resume_text = models.TextField(blank=True)
    resume_hash = models.CharField(max_length=64, blank=True)
    resume_parsed_at = models.DateTimeField(null=True, blank=True)
    headline = models.CharField(max_length=200, blank=True)
    skills = models.ManyToManyField(Skill, blank=True, related_name="candidates")
    share_in_pool = models.BooleanField(default=False)

    class Meta:
        ordering = ["user__email"]

    def __str__(self):
        return self.user.email

    def save(self, *args, **kwargs):
        """Delete the previously stored résumé when it is replaced or cleared."""
        old_file = None
        if self.pk:
            old_file = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("resume", flat=True)
                .first()
            )
        super().save(*args, **kwargs)
        new_name = self.resume.name or ""
        if old_file and old_file != new_name:
            try:
                self.resume.storage.delete(old_file)
            except Exception:  # pragma: no cover - storage cleanup is best-effort
                pass

    @property
    def display_name(self):
        """Best available human name: the user's full name, else their email.

        ``CandidateProfile`` carries no name of its own, so the only names we
        ever have come from ``core.User.first_name/last_name`` — which are
        optional, hence the email fallback.
        """
        full = (self.user.get_full_name() or "").strip()
        return full or self.user.email


class Application(models.Model):
    """A candidate's application to a job, tracked through the pipeline."""

    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    HIRED = "HIRED"
    WITHDRAWN = "WITHDRAWN"
    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (REJECTED, "Rejected"),
        (HIRED, "Hired"),
        (WITHDRAWN, "Withdrawn"),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="applications")
    candidate = models.ForeignKey(
        CandidateProfile, on_delete=models.CASCADE, related_name="applications"
    )
    current_stage = models.ForeignKey(
        PipelineStage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applications",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    ai_summary = models.TextField(blank=True)
    ai_fit_score = models.PositiveSmallIntegerField(null=True, blank=True)
    ai_details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "candidate"], name="uniq_application_per_job_candidate"
            )
        ]

    def __str__(self):
        return f"{self.candidate} → {self.job}"

    @property
    def company(self):
        return self.job.company

    def advance(self):
        """Move to the next pipeline stage, or mark HIRED at the last stage."""
        if self.status != self.ACTIVE:
            return self
        next_stage = None
        if self.current_stage is not None:
            next_stage = self.current_stage.next_stage()
        else:
            next_stage = self.job.first_stage
        if next_stage is None:
            self.status = self.HIRED
        else:
            self.current_stage = next_stage
        self.save(update_fields=["current_stage", "status", "updated_at"])
        return self

    def reject(self):
        self.status = self.REJECTED
        self.save(update_fields=["status", "updated_at"])
        return self


class StageReview(models.Model):
    """One reviewer's verdict on an application at a given stage."""

    PASS = "PASS"
    FAIL = "FAIL"
    HOLD = "HOLD"
    DECISION_CHOICES = [
        (PASS, "Pass"),
        (FAIL, "Fail"),
        (HOLD, "Hold"),
    ]

    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="reviews"
    )
    stage = models.ForeignKey(
        PipelineStage, on_delete=models.CASCADE, related_name="reviews"
    )
    reviewer = models.ForeignKey(
        "core.User", on_delete=models.CASCADE, related_name="stage_reviews"
    )
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES, default=HOLD)
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "stage", "reviewer"], name="uniq_review_per_reviewer"
            )
        ]

    def __str__(self):
        return f"{self.stage.name}: {self.decision} by {self.reviewer}"
