"""Models for the video app: one-way (asynchronous) video screening.

A recruiter builds a :class:`VideoScreen` for a job stage out of reusable
:class:`VideoQuestion` rows. When an application lands on that stage a
:class:`VideoInvite` is created (tokenised, deadline-bound) and the candidate
records one :class:`VideoResponse` per question in the browser.
"""

import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# Upload limits enforced by the upload view and the model validators.
MAX_RESPONSE_BYTES = 200 * 1024 * 1024  # 200 MB
ALLOWED_MIME_TYPES = ("video/webm", "video/mp4")
ALLOWED_EXTENSIONS = ("webm", "mp4")


def normalise_mime(value):
    """Strip codec parameters: ``video/webm;codecs=vp8,opus`` -> ``video/webm``."""
    return (value or "").split(";")[0].strip().lower()


class VideoQuestion(models.Model):
    """A reusable prompt in a company's video-screening question library."""

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="video_questions"
    )
    text = models.TextField()
    think_seconds = models.PositiveIntegerField(
        default=30, help_text="Seconds the candidate gets to prepare before recording starts."
    )
    answer_seconds = models.PositiveIntegerField(
        default=120, help_text="Maximum recording length in seconds."
    )
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text[:60]


class VideoScreen(models.Model):
    """A set of video questions attached to a job (optionally to one stage)."""

    job = models.ForeignKey(
        "jobs.Job", on_delete=models.CASCADE, related_name="video_screens"
    )
    stage = models.ForeignKey(
        "jobs.PipelineStage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="video_screens",
    )
    title = models.CharField(max_length=150)
    questions = models.ManyToManyField(
        VideoQuestion, through="VideoScreenQuestion", related_name="screens"
    )
    deadline_days = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["job_id", "id"]

    def __str__(self):
        return self.title

    @property
    def company(self):
        return self.job.company

    def ordered_questions(self):
        """Questions in the order the recruiter arranged them."""
        return self.questions.order_by("screenquestion_links__order", "screenquestion_links__id")


class VideoScreenQuestion(models.Model):
    """Through model giving each question a position inside a screen."""

    screen = models.ForeignKey(
        VideoScreen, on_delete=models.CASCADE, related_name="question_links"
    )
    question = models.ForeignKey(
        VideoQuestion, on_delete=models.CASCADE, related_name="screenquestion_links"
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("screen", "question")]

    def __str__(self):
        return f"{self.screen_id}#{self.order}"


class VideoInvite(models.Model):
    """A candidate's tokenised invitation to complete a video screen."""

    TOKEN_BYTES = 32

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (IN_PROGRESS, "In progress"),
        (SUBMITTED, "Submitted"),
        (EXPIRED, "Expired"),
    ]

    application = models.ForeignKey(
        "jobs.Application", on_delete=models.CASCADE, related_name="video_invites"
    )
    screen = models.ForeignKey(
        VideoScreen, on_delete=models.CASCADE, related_name="invites"
    )
    token = models.CharField(max_length=100, unique=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("application", "screen")]

    def __str__(self):
        return f"{self.application_id} -> {self.screen.title}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self.new_token()
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(
                days=self.screen.deadline_days if self.screen_id else 5
            )
        super().save(*args, **kwargs)

    @staticmethod
    def new_token():
        return secrets.token_urlsafe(VideoInvite.TOKEN_BYTES)

    @property
    def company(self):
        return self.application.job.company

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_open(self):
        """True when the candidate may still record against this invite."""
        return self.status in (self.PENDING, self.IN_PROGRESS) and not self.is_expired

    def answered_question_ids(self):
        return set(self.responses.values_list("question_id", flat=True))

    def next_question(self):
        """The first unanswered question of the screen, or ``None`` when done."""
        answered = self.answered_question_ids()
        for question in self.screen.ordered_questions():
            if question.id not in answered:
                return question
        return None

    def mark_started(self):
        if self.status == self.PENDING:
            self.status = self.IN_PROGRESS
            self.started_at = timezone.now()
            self.save(update_fields=["status", "started_at"])

    def mark_submitted(self):
        self.status = self.SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=["status", "submitted_at"])

    def mark_expired(self):
        if self.status in (self.PENDING, self.IN_PROGRESS):
            self.status = self.EXPIRED
            self.save(update_fields=["status"])

    @property
    def progress(self):
        total = self.screen.questions.count()
        return {"answered": self.responses.count(), "total": total}


def validate_response_file(value):
    """Reject oversized files and unsupported container extensions."""
    size = getattr(value, "size", None)
    if size is not None and size > MAX_RESPONSE_BYTES:
        raise ValidationError("Video is larger than the 200 MB limit.")
    name = (getattr(value, "name", "") or "").lower()
    if name and not name.endswith(tuple(f".{e}" for e in ALLOWED_EXTENSIONS)):
        raise ValidationError("Only .webm and .mp4 recordings are accepted.")


class VideoResponse(models.Model):
    """One recorded answer, plus its transcript and AI review."""

    UPLOADED = "UPLOADED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    STATUS_CHOICES = [
        (UPLOADED, "Uploaded"),
        (PROCESSED, "Processed"),
        (FAILED, "Failed"),
    ]

    invite = models.ForeignKey(
        VideoInvite, on_delete=models.CASCADE, related_name="responses"
    )
    question = models.ForeignKey(
        VideoQuestion, on_delete=models.CASCADE, related_name="responses"
    )
    file = models.FileField(
        upload_to="video/%Y/%m/", validators=[validate_response_file]
    )
    duration_seconds = models.PositiveIntegerField(default=0)
    mime = models.CharField(max_length=100, blank=True)
    transcript = models.TextField(blank=True)
    ai_summary = models.TextField(blank=True)
    ai_score = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=UPLOADED)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["question__order", "id"]
        unique_together = [("invite", "question")]

    def __str__(self):
        return f"response {self.pk} for invite {self.invite_id}"

    @property
    def company(self):
        return self.invite.company

    @property
    def minutes_billed(self):
        """VIDEO_MINUTE units consumed by this response (rounded up)."""
        import math

        return max(1, math.ceil((self.duration_seconds or 0) / 60))
