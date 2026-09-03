"""Serializers for the v1 API."""

from django.contrib.auth import authenticate
from rest_framework import serializers

from assessments.models import Assessment, Attempt, Question
from core.models import Company, Membership, User
from jobs.models import (
    Application,
    CandidateProfile,
    Job,
    PipelineStage,
    Skill,
    StageReview,
)


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
