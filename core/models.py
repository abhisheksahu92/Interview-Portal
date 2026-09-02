import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
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


class Invitation(models.Model):
    """A pending invitation for an email address to join a company."""

    TOKEN_BYTES = 32
    EXPIRY_DAYS = 7

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField()
    role = models.CharField(
        max_length=20, choices=Membership.ROLE_CHOICES, default=Membership.RECRUITER
    )
    token = models.CharField(max_length=100, unique=True)
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invitations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} -> {self.company.name} ({self.role})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self.new_token()
        if self.email:
            self.email = self.email.strip().lower()
        if not self.expires_at:
            self.expires_at = self.default_expiry()
        super().save(*args, **kwargs)

    @staticmethod
    def new_token():
        return secrets.token_urlsafe(Invitation.TOKEN_BYTES)

    @classmethod
    def default_expiry(cls):
        return timezone.now() + timedelta(days=cls.EXPIRY_DAYS)

    @property
    def is_accepted(self):
        return self.accepted_at is not None

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_pending(self):
        return not self.is_accepted and not self.is_expired

    def accept_url(self, request=None):
        from django.urls import reverse

        path = reverse("core:invite_accept", args=[self.token])
        return request.build_absolute_uri(path) if request is not None else path

    def refresh_token(self):
        """Issue a new token and push the expiry out (used by "resend")."""
        self.token = self.new_token()
        self.expires_at = self.default_expiry()
        self.accepted_at = None
        self.save(update_fields=["token", "expires_at", "accepted_at"])
        return self

    def accept(self, user):
        """Create/update the Membership for ``user`` and mark this accepted."""
        membership, created = Membership.objects.get_or_create(
            user=user, company=self.company, defaults={"role": self.role}
        )
        if not created and membership.role != self.role:
            membership.role = self.role
            membership.save(update_fields=["role"])
        self.accepted_at = timezone.now()
        self.save(update_fields=["accepted_at"])
        return membership
