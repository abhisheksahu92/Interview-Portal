"""Assessment models: skill-tagged question bank, per-stage assessments, attempts."""

from decimal import Decimal

from django.db import models
from django.utils import timezone


class Question(models.Model):
    """A single bank question, owned by a company and optionally skill-tagged."""

    MCQ = "MCQ"
    TEXT = "TEXT"
    KIND_CHOICES = [(MCQ, "Multiple choice"), (TEXT, "Free text")]

    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    DIFFICULTY_CHOICES = [(EASY, "Easy"), (MEDIUM, "Medium"), (HARD, "Hard")]

    MANUAL = "MANUAL"
    AI = "AI"
    MARKETPLACE = "MARKETPLACE"
    SOURCE_CHOICES = [(MANUAL, "Manual"), (AI, "AI generated"), (MARKETPLACE, "Marketplace")]

    company = models.ForeignKey(
        "core.Company", on_delete=models.CASCADE, related_name="questions"
    )
    skill = models.ForeignKey(
        "jobs.Skill",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=MCQ)
    text = models.TextField()
    options = models.JSONField(default=list, blank=True)
    correct_option = models.PositiveSmallIntegerField(null=True, blank=True)
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_CHOICES, default=MEDIUM
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"[{self.kind}] {self.text[:60]}"

    @property
    def is_mcq(self):
        return self.kind == self.MCQ


class Assessment(models.Model):
    """A timed set of questions attached to a job (and usually a pipeline stage)."""

    job = models.ForeignKey(
        "jobs.Job", on_delete=models.CASCADE, related_name="assessments"
    )
    stage = models.ForeignKey(
        "jobs.PipelineStage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assessments",
    )
    title = models.CharField(max_length=200)
    questions = models.ManyToManyField(Question, blank=True, related_name="assessments")
    time_limit_minutes = models.PositiveIntegerField(default=30)
    pass_mark_percent = models.PositiveSmallIntegerField(default=60)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["job_id", "id"]

    def __str__(self):
        return self.title

    @property
    def company(self):
        return self.job.company


class Attempt(models.Model):
    """One candidate application's attempt at an assessment."""

    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="attempts"
    )
    application = models.ForeignKey(
        "jobs.Application", on_delete=models.CASCADE, related_name="attempts"
    )
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)
    score_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    passed = models.BooleanField(null=True, blank=True)
    ai_feedback = models.TextField(blank=True)
    needs_review = models.BooleanField(
        default=False,
        help_text="A free-text answer could not be graded automatically.",
    )
    manual_scores = models.JSONField(
        default=dict,
        blank=True,
        help_text="Recruiter-entered {question_id: 0-100} scores for TEXT answers.",
    )
    pending_review = models.JSONField(
        default=list,
        blank=True,
        help_text="Question ids still awaiting a manual score.",
    )

    class Meta:
        ordering = ["-started_at"]
        unique_together = [("assessment", "application")]

    def __str__(self):
        return f"{self.application_id} @ {self.assessment_id}"

    @property
    def company(self):
        return self.assessment.job.company

    @property
    def deadline(self):
        return self.started_at + timezone.timedelta(
            minutes=self.assessment.time_limit_minutes
        )

    @property
    def is_expired(self):
        return self.submitted_at is None and timezone.now() > self.deadline

    @property
    def seconds_remaining(self):
        return max(0, int((self.deadline - timezone.now()).total_seconds()))

    @property
    def pending_review_count(self):
        return len(self.pending_review or [])

    def pending_questions(self):
        """Questions still awaiting a manual score, in assessment order."""
        ids = [int(pk) for pk in (self.pending_review or [])]
        if not ids:
            return []
        by_pk = {q.pk: q for q in self.assessment.questions.filter(pk__in=ids)}
        return [by_pk[pk] for pk in ids if pk in by_pk]

    def set_manual_score(self, question, score):
        """Record a recruiter score (0-100) for one TEXT answer and regrade."""
        score = int(score)
        if not 0 <= score <= 100:
            raise ValueError("Manual scores must be between 0 and 100.")
        scores = dict(self.manual_scores or {})
        scores[str(question.pk)] = score
        self.manual_scores = scores
        self.save(update_fields=["manual_scores"])
        return self.grade()

    def grade(self):
        """Score the attempt: MCQs locally, free text via ``assessments.ai``.

        Ungradable free-text answers (no API key, or the model declined) are left
        out of the denominator and flag the attempt for manual review instead of
        silently counting as zero.
        """
        from assessments import ai

        questions = list(self.assessment.questions.all())
        if not questions:
            self.score_percent = Decimal("0.00")
            self.passed = False
            self.needs_review = False
            self.pending_review = []
            self.save(
                update_fields=["score_percent", "passed", "needs_review", "pending_review"]
            )
            return self.score_percent

        total = Decimal(0)
        graded = 0
        notes = []
        pending = []
        manual = self.manual_scores or {}
        for position, question in enumerate(questions, start=1):
            answer = self.answers.get(str(question.pk), self.answers.get(question.pk))
            if question.is_mcq:
                graded += 1
                try:
                    chosen = int(answer)
                except (TypeError, ValueError):
                    chosen = None
                if chosen is not None and chosen == question.correct_option:
                    total += Decimal(100)
                continue

            score = manual.get(str(question.pk), manual.get(question.pk))
            source = "Manual"
            if score is None:
                source = "AI"
                score = ai.grade_text_answer(question, str(answer)) if answer else None
            if score is None:
                pending.append(question.pk)
                notes.append(f"Q{position}: pending manual review.")
            else:
                graded += 1
                total += Decimal(int(score))
                notes.append(f"Q{position}: {source} score {int(score)}/100.")

        self.pending_review = pending
        self.needs_review = bool(pending)
        if graded:
            self.score_percent = (total / Decimal(graded)).quantize(Decimal("0.01"))
            self.passed = self.score_percent >= Decimal(
                self.assessment.pass_mark_percent
            )
        else:
            # Nothing gradable yet: leave the result open for the hiring team.
            self.score_percent = None
            self.passed = None
        if notes:
            self.ai_feedback = "\n".join(notes)
        self.save(
            update_fields=[
                "score_percent",
                "passed",
                "ai_feedback",
                "needs_review",
                "pending_review",
            ]
        )
        return self.score_percent
