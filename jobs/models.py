"""Jobs domain models: skills, jobs, pipeline stages, candidates, applications."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Skill(models.Model):
    """A per-company skill tag (never a hardcoded choice list)."""

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="skills"
    )
    name = models.CharField(max_length=80)

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

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="jobs"
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
    resume = models.FileField(upload_to="resumes/", blank=True)
    resume_text = models.TextField(blank=True)
    resume_hash = models.CharField(max_length=64, blank=True)
    resume_parsed_at = models.DateTimeField(null=True, blank=True)
    headline = models.CharField(max_length=200, blank=True)
    skills = models.ManyToManyField(Skill, blank=True, related_name="candidates")

    class Meta:
        ordering = ["user__email"]

    def __str__(self):
        return self.user.email


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
