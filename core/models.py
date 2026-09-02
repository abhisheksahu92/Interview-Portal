from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.text import slugify


class Company(models.Model):
    """A tenant: one hiring organisation."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.unique_slug(self.name)
        super().save(*args, **kwargs)

    @classmethod
    def unique_slug(cls, name):
        base = slugify(name) or "company"
        slug = base
        i = 2
        while cls.objects.filter(slug=slug).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug


class UserManager(BaseUserManager):
    """Manager for the email-as-username user model."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("Superuser must have is_staff and is_superuser set.")
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Email-login user. `username` is kept but optional and non-unique."""

    username = models.CharField(max_length=150, blank=True, default="", unique=False)
    email = models.EmailField("email address", unique=True)
    is_candidate = models.BooleanField(
        default=False,
        help_text="True for external job applicants (no company membership).",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list = []
    EMAIL_FIELD = "email"

    objects = UserManager()

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email

    @property
    def companies(self):
        return Company.objects.filter(memberships__user=self)

    def membership_for(self, company):
        if company is None:
            return None
        return self.memberships.filter(company=company).first()

    def role_in(self, company):
        membership = self.membership_for(company)
        return membership.role if membership else None


class Membership(models.Model):
    """Links a user to a company with a role."""

    OWNER = "OWNER"
    RECRUITER = "RECRUITER"
    INTERVIEWER = "INTERVIEWER"

    ROLE_CHOICES = [
        (OWNER, "Owner"),
        (RECRUITER, "Recruiter"),
        (INTERVIEWER, "Interviewer"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=RECRUITER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "company")]
        ordering = ["company__name", "user__email"]

    def __str__(self):
        return f"{self.user.email} @ {self.company.name} ({self.role})"
