"""Careers-site models: the public branded site and per-job board distribution."""

from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

hex_color = RegexValidator(
    r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$",
    "Enter a hex colour such as #2563eb.",
)


class CareersSite(models.Model):
    """One public, brandable careers page per company."""

    company = models.OneToOneField(
        "core.Company", on_delete=models.CASCADE, related_name="careers_site"
    )
    slug = models.SlugField(max_length=60, unique=True)
    custom_domain = models.CharField(
        max_length=253,
        blank=True,
        null=True,
        unique=True,
        help_text="e.g. careers.example.com — point a CNAME at this app and add "
        "the host to ALLOWED_HOSTS.",
    )
    headline = models.CharField(max_length=200, blank=True)
    about = models.TextField(
        blank=True, help_text="Plain text with blank lines for paragraphs and '- ' for lists."
    )
    brand_color = models.CharField(max_length=7, default="#2563eb", validators=[hex_color])
    logo = models.ImageField(upload_to="careers/logos/", blank=True)
    hero_image = models.ImageField(upload_to="careers/heroes/", blank=True)
    published = models.BooleanField(default=False)
    list_in_network = models.BooleanField(
        default=True,
        help_text="Also list this site's open roles on the public cross-tenant job board.",
    )
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=200, blank=True)
    show_salary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "careers site"

    def __str__(self):
        return self.slug

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug(
                getattr(self.company, "slug", "") or slugify(self.company.name) or "careers"
            )
        if not self.custom_domain:
            # "" would collide across rows under the unique constraint.
            self.custom_domain = None
        else:
            self.custom_domain = self.custom_domain.strip().lower()
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("careers:site", args=[self.slug])

    def _unique_slug(self, base):
        base = slugify(base)[:55] or "careers"
        slug, i = base, 2
        while CareersSite.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"[:60]
            i += 1
        return slug

    @classmethod
    def for_host(cls, host):
        """The published site served on ``host`` (custom domain), or None."""
        host = (host or "").split(":")[0].strip().lower()
        if not host:
            return None
        return cls.objects.filter(published=True, custom_domain=host).first()

    @property
    def title(self):
        return self.seo_title or f"Careers at {self.company.name}"

    def open_jobs(self):
        from jobs.models import Job

        return (
            Job.objects.filter(company=self.company, status=Job.OPEN)
            .prefetch_related("skills")
            .order_by("-created_at")
        )


class JobDistribution(models.Model):
    """The state of one job on one external job board."""

    LINKEDIN = "LINKEDIN"
    INDEED = "INDEED"
    NAUKRI = "NAUKRI"
    GOOGLE_JOBS = "GOOGLE_JOBS"
    BOARD_CHOICES = [
        (LINKEDIN, "LinkedIn"),
        (INDEED, "Indeed"),
        (NAUKRI, "Naukri"),
        (GOOGLE_JOBS, "Google for Jobs"),
    ]

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    FAILED = "FAILED"
    REMOVED = "REMOVED"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (POSTED, "Posted"),
        (FAILED, "Failed"),
        (REMOVED, "Removed"),
    ]

    job = models.ForeignKey(
        "jobs.Job", on_delete=models.CASCADE, related_name="distributions"
    )
    board = models.CharField(max_length=20, choices=BOARD_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    external_id = models.CharField(max_length=200, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["board"]
        constraints = [
            models.UniqueConstraint(fields=["job", "board"], name="uniq_distribution_per_board")
        ]

    def __str__(self):
        return f"{self.job_id}:{self.board}"
