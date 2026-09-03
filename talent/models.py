"""Talent-pool models: sourced profiles and bulk-import batches."""

from django.db import models

from core.permissions import for_company


def normalize_email(value):
    """Lowercased, stripped email (empty string when falsy)."""
    return (value or "").strip().lower()


class CompanyScopedQuerySet(models.QuerySet):
    def for_company(self, company):
        return for_company(self, company)


class TalentProfile(models.Model):
    """A sourced candidate in one company's private talent pool."""

    MANUAL = "MANUAL"
    IMPORT = "IMPORT"
    APPLICANT = "APPLICANT"
    REFERRAL = "REFERRAL"
    SOURCE_CHOICES = [
        (MANUAL, "Manual"),
        (IMPORT, "Import"),
        (APPLICANT, "Applicant"),
        (REFERRAL, "Referral"),
    ]

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="talent_profiles"
    )
    email = models.EmailField()
    name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    headline = models.CharField(max_length=200, blank=True)
    experience_years = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    current_company = models.CharField(max_length=150, blank=True)
    location = models.CharField(max_length=150, blank=True)
    resume = models.FileField(upload_to="talent/", blank=True)
    resume_text = models.TextField(blank=True)
    skills = models.ManyToManyField("jobs.Skill", blank=True, related_name="talent_profiles")
    tags = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=MANUAL)
    notes = models.TextField(blank=True)
    last_contacted = models.DateTimeField(null=True, blank=True)
    linked_candidate = models.ForeignKey(
        "jobs.CandidateProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="talent_profiles",
    )
    created_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sourced_talent",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "email"], name="talent_unique_company_email"
            )
        ]
        indexes = [models.Index(fields=["company", "email"])]

    def __str__(self):
        return self.name or self.email

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        if not isinstance(self.tags, list):
            self.tags = []
        self.tags = [str(t).strip() for t in self.tags if str(t).strip()]
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.name or self.email

    def add_tag(self, tag):
        """Append ``tag`` (case-insensitive, deduped). Returns True when added."""
        tag = str(tag or "").strip()
        if not tag:
            return False
        existing = {t.lower() for t in (self.tags or [])}
        if tag.lower() in existing:
            return False
        self.tags = list(self.tags or []) + [tag]
        self.save(update_fields=["tags", "updated_at"])
        return True

    def applications(self):
        """Applications visible for this profile (via the linked candidate)."""
        from jobs.models import Application

        if self.linked_candidate_id is None:
            return Application.objects.none()
        return (
            Application.objects.filter(
                candidate_id=self.linked_candidate_id, job__company_id=self.company_id
            )
            .select_related("job", "current_stage")
            .order_by("-created_at")
        )


class ImportBatch(models.Model):
    """One bulk-import run (zip / multiple resumes / CSV)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (RUNNING, "Running"),
        (DONE, "Done"),
        (FAILED, "Failed"),
    ]

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="talent_imports"
    )
    uploaded_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="talent_imports",
    )
    file = models.FileField(upload_to="talent/imports/", blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    total = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    updated = models.PositiveIntegerField(default=0)
    skipped = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "import batches"

    def __str__(self):
        return f"Import #{self.pk} ({self.status})"

    @property
    def processed(self):
        return self.created + self.updated + self.skipped

    @property
    def percent(self):
        if not self.total:
            return 100 if self.status in {self.DONE, self.FAILED} else 0
        return min(100, int(round(100 * self.processed / self.total)))

    @property
    def is_finished(self):
        return self.status in {self.DONE, self.FAILED}

    def note_error(self, label, message):
        self.errors = list(self.errors or []) + [{"item": str(label), "error": str(message)}]
