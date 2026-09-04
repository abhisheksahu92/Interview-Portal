"""Serializers for the v1 API."""

from django.contrib.auth import authenticate
from rest_framework import serializers

from assessments.models import Assessment, Attempt, Question
from clients.models import Submission
from core.models import Company, Membership, User
from integrations.events import EVENTS
from integrations.models import OutboundWebhook
from jobs.models import (
    Application,
    CandidateProfile,
    Job,
    PipelineStage,
    Skill,
    StageReview,
)
from offers.models import Offer, OfferTemplate
from scheduling.models import Interview
from talent.models import TalentProfile
from video.models import VideoInvite


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "slug", "created_at"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_candidate"]
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    company = CompanySerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "company", "role", "created_at"]
        read_only_fields = fields


class AuthTokenSerializer(serializers.Serializer):
    """Email + password exchange for a DRF auth token."""

    email = serializers.EmailField()
    password = serializers.CharField(style={"input_type": "password"}, write_only=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"],
            password=attrs["password"],
        )
        if user is None or not user.is_active:
            raise serializers.ValidationError("Invalid email or password.")
        attrs["user"] = user
        return attrs


class CompanyScopedSerializer(serializers.ModelSerializer):
    """Injects the resolved company on create."""

    def create(self, validated_data):
        validated_data.setdefault("company", self.context.get("company"))
        return super().create(validated_data)


class SkillSerializer(CompanyScopedSerializer):
    class Meta:
        model = Skill
        fields = ["id", "name"]

    def validate_name(self, value):
        company = self.context.get("company")
        qs = Skill.objects.filter(company=company, name__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This skill already exists.")
        return value


class PipelineStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineStage
        fields = ["id", "job", "name", "order", "kind", "requires_assessment"]


class NestedPipelineStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineStage
        fields = ["id", "name", "order", "kind", "requires_assessment"]


class JobSerializer(CompanyScopedSerializer):
    stages = NestedPipelineStageSerializer(many=True, read_only=True)
    skill_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Skill.objects.all(),
        source="skills",
        required=False,
        write_only=True,
    )
    skills = SkillSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "title",
            "location",
            "description",
            "requirements",
            "employment_type",
            "status",
            "skills",
            "skill_ids",
            "stages",
            "created_by",
            "created_at",
            "closes_at",
        ]
        read_only_fields = ["created_by", "created_at"]

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class CandidateProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    skill_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Skill.objects.all(),
        source="skills",
        required=False,
        write_only=True,
    )
    skills = SkillSerializer(many=True, read_only=True)

    class Meta:
        model = CandidateProfile
        fields = [
            "id",
            "user",
            "phone",
            "date_of_birth",
            "experience_years",
            "notice_period_days",
            "resume",
            "headline",
            "skills",
            "skill_ids",
        ]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class StageReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = StageReview
        fields = [
            "id",
            "application",
            "stage",
            "reviewer",
            "decision",
            "rating",
            "feedback",
            "created_at",
        ]
        read_only_fields = ["reviewer", "created_at"]

    def create(self, validated_data):
        validated_data["reviewer"] = self.context["request"].user
        return super().create(validated_data)


class ApplicationSerializer(serializers.ModelSerializer):
    candidate_detail = CandidateProfileSerializer(source="candidate", read_only=True)
    current_stage_detail = NestedPipelineStageSerializer(
        source="current_stage", read_only=True
    )
    reviews = StageReviewSerializer(many=True, read_only=True)

    class Meta:
        model = Application
        fields = [
            "id",
            "job",
            "candidate",
            "candidate_detail",
            "current_stage",
            "current_stage_detail",
            "status",
            "ai_summary",
            "ai_fit_score",
            "reviews",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["ai_summary", "ai_fit_score", "created_at", "updated_at"]


class ApplicationReviewSerializer(serializers.Serializer):
    """Payload for the ``review`` action on an application."""

    decision = serializers.ChoiceField(choices=["PASS", "FAIL", "HOLD"])
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    feedback = serializers.CharField(required=False, allow_blank=True)
    stage = serializers.PrimaryKeyRelatedField(
        queryset=PipelineStage.objects.all(), required=False
    )


class QuestionSerializer(CompanyScopedSerializer):
    class Meta:
        model = Question
        fields = [
            "id",
            "skill",
            "kind",
            "text",
            "options",
            "correct_option",
            "difficulty",
            "source",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class AssessmentSerializer(serializers.ModelSerializer):
    question_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Question.objects.all(),
        source="questions",
        required=False,
        write_only=True,
    )
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Assessment
        fields = [
            "id",
            "job",
            "stage",
            "title",
            "questions",
            "question_ids",
            "time_limit_minutes",
            "pass_mark_percent",
            "is_active",
        ]


class AttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attempt
        fields = [
            "id",
            "assessment",
            "application",
            "started_at",
            "submitted_at",
            "answers",
            "score_percent",
            "passed",
            "ai_feedback",
        ]
        read_only_fields = [
            "started_at",
            "submitted_at",
            "score_percent",
            "passed",
            "ai_feedback",
        ]


class AttemptStartSerializer(serializers.Serializer):
    assessment = serializers.PrimaryKeyRelatedField(queryset=Assessment.objects.all())
    application = serializers.PrimaryKeyRelatedField(queryset=Application.objects.all())


class AttemptSubmitSerializer(serializers.Serializer):
    answers = serializers.DictField(required=False)


# --- Phase 3 -------------------------------------------------------------
# These endpoints are read-mostly integration surfaces, so the serializers
# expose flat, stable, mostly read-only shapes rather than nested writable
# graphs. Writes are limited to what an external system legitimately needs:
# create a draft offer, add a talent profile, manage webhooks.

class ApplicationBriefSerializer(serializers.ModelSerializer):
    """Compact application reference embedded in phase-3 payloads."""

    job_title = serializers.CharField(source="job.title", read_only=True)
    candidate_email = serializers.EmailField(source="candidate.user.email", read_only=True)
    stage = serializers.CharField(source="current_stage.name", read_only=True, default=None)

    class Meta:
        model = Application
        fields = ["id", "status", "job", "job_title", "candidate_email", "stage"]
        read_only_fields = fields


class InterviewSerializer(serializers.ModelSerializer):
    application_detail = ApplicationBriefSerializer(source="application", read_only=True)
    interviewer_emails = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = [
            "id",
            "application",
            "application_detail",
            "stage",
            "status",
            "scheduled_start",
            "scheduled_end",
            "duration_minutes",
            "timezone",
            "location_or_link",
            "interviewer_emails",
            "created_at",
        ]
        read_only_fields = fields

    def get_interviewer_emails(self, obj) -> list[str]:
        return [user.email for user in obj.interviewers.all()]


class OfferSerializer(serializers.ModelSerializer):
    application_detail = ApplicationBriefSerializer(source="application", read_only=True)

    class Meta:
        model = Offer
        fields = [
            "id",
            "application",
            "application_detail",
            "template",
            "salary",
            "currency",
            "joining_date",
            "expires_at",
            "status",
            "signed_name",
            "signed_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "application_detail",
            "status",
            "signed_name",
            "signed_at",
            "created_at",
        ]

    def validate_application(self, application):
        company = self.context.get("company")
        if company is None or application.company != company:
            raise serializers.ValidationError("Unknown application for this company.")
        return application

    def validate_template(self, template):
        company = self.context.get("company")
        if template is not None and template.company != company:
            raise serializers.ValidationError("Unknown template for this company.")
        return template

    def create(self, validated_data):
        """API-created offers always start as DRAFT.

        Sending an offer has side effects (email, e-sign token, audit trail)
        that belong to the offers app's own flow, so the API can stage the
        paperwork but a human still presses send.
        """
        company = self.context.get("company")
        validated_data["status"] = Offer.DRAFT
        if validated_data.get("template") is None:
            validated_data["template"] = OfferTemplate.default_for(company)
        return super().create(validated_data)


class SubmissionSerializer(serializers.ModelSerializer):
    application_detail = ApplicationBriefSerializer(source="application", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)

    class Meta:
        model = Submission
        fields = [
            "id",
            "application",
            "application_detail",
            "client",
            "client_name",
            "status",
            "note",
            "client_feedback",
            "client_rating",
            "decided_at",
            "created_at",
        ]
        read_only_fields = fields


class VideoInviteSerializer(serializers.ModelSerializer):
    application_detail = ApplicationBriefSerializer(source="application", read_only=True)
    screen_title = serializers.SerializerMethodField()

    class Meta:
        model = VideoInvite
        fields = [
            "id",
            "application",
            "application_detail",
            "screen",
            "screen_title",
            "status",
            "expires_at",
            "started_at",
            "submitted_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_screen_title(self, obj) -> str:
        return str(obj.screen)


class TalentProfileSerializer(CompanyScopedSerializer):
    skill_names = serializers.SerializerMethodField()

    class Meta:
        model = TalentProfile
        fields = [
            "id",
            "email",
            "name",
            "phone",
            "headline",
            "experience_years",
            "current_company",
            "location",
            "skills",
            "skill_names",
            "tags",
            "source",
            "notes",
            "last_contacted",
            "created_at",
        ]
        read_only_fields = ["id", "skill_names", "created_at"]

    def get_skill_names(self, obj) -> list[str]:
        return [skill.name for skill in obj.skills.all()]

    def validate_email(self, value):
        company = self.context.get("company")
        qs = TalentProfile.objects.filter(company=company, email__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A talent profile with this email exists.")
        return value


class OutboundWebhookSerializer(CompanyScopedSerializer):
    """Webhook CRUD. ``secret`` is write-once: returned only on create."""

    events = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    secret = serializers.CharField(read_only=True)

    class Meta:
        model = OutboundWebhook
        fields = ["id", "name", "url", "events", "active", "secret", "created_at"]
        read_only_fields = ["id", "secret", "created_at"]

    def validate_events(self, value):
        unknown = [name for name in value if name not in EVENTS]
        if unknown:
            raise serializers.ValidationError(
                f"Unknown events: {', '.join(unknown)}. Known: {', '.join(EVENTS)}."
            )
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Only the create response reveals the plaintext secret; later reads
        # get a masked hint so a leaked GET cannot forge signatures.
        if not getattr(self, "_reveal_secret", False):
            data["secret"] = instance.masked_secret
        return data
