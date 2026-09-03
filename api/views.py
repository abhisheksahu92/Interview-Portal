"""ViewSets for the v1 API. Everything is scoped to the resolved company."""

from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from api.mixins import CompanyScopedViewSetMixin
from api.permissions import (
    IsCompanyMember,
    IsInterviewer,
    IsRecruiterOrOwner,
)
from api.serializers import (
    ApplicationReviewSerializer,
    ApplicationSerializer,
    AssessmentSerializer,
    AttemptSerializer,
    AttemptStartSerializer,
    AttemptSubmitSerializer,
    AuthTokenSerializer,
    CandidateProfileSerializer,
    CompanySerializer,
    JobSerializer,
    MembershipSerializer,
    PipelineStageSerializer,
    QuestionSerializer,
    SkillSerializer,
    StageReviewSerializer,
)
from assessments.models import Assessment, Attempt, Question
from core.models import Company, Membership
from jobs.models import (
    Application,
    CandidateProfile,
    Job,
    PipelineStage,
    Skill,
    StageReview,
)


class AuthTokenView(APIView):
    """POST email/password -> {"token": ..., "user": {...}, "companies": [...]}."""

    authentication_classes: list = []
    permission_classes: list = []
    serializer_class = AuthTokenSerializer

    def post(self, request):
        serializer = AuthTokenSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user": {"id": user.pk, "email": user.email},
                "companies": CompanySerializer(user.companies, many=True).data,
            }
        )


class CompanyViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Read-only list of the companies the caller belongs to."""

    serializer_class = CompanySerializer
    queryset = Company.objects.all()

    def get_queryset(self):
        return Company.objects.filter(memberships__user=self.request.user).distinct()


class MembershipViewSet(
    CompanyScopedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only membership list for the active company."""

    serializer_class = MembershipSerializer
    permission_classes = [IsCompanyMember]
    queryset = Membership.objects.select_related("user", "company")


class SkillViewSet(CompanyScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = SkillSerializer
    permission_classes = [IsRecruiterOrOwner]
    queryset = Skill.objects.all()


class JobViewSet(CompanyScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = JobSerializer
    permission_classes = [IsRecruiterOrOwner]
    queryset = Job.objects.prefetch_related("stages", "skills")
    filterset_fields: list = []

    def get_queryset(self):
        qs = super().get_queryset()
        job_status = self.request.query_params.get("status")
        if job_status:
            qs = qs.filter(status=job_status)
        return qs

    @action(detail=True, methods=["get"])
    def stages(self, request, pk=None):
        job = self.get_object()
        data = PipelineStageSerializer(job.stages.all(), many=True).data
        return Response(data)


class PipelineStageViewSet(CompanyScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = PipelineStageSerializer
    permission_classes = [IsRecruiterOrOwner]
    queryset = PipelineStage.objects.select_related("job")
    company_field = "job__company"

    def get_queryset(self):
        qs = super().get_queryset()
        job_id = self.request.query_params.get("job")
        if job_id:
            qs = qs.filter(job_id=job_id)
        return qs


class CandidateProfileViewSet(viewsets.ModelViewSet):
    """Candidates see/edit only their own profile; company members see the
    profiles that applied to their jobs."""

    serializer_class = CandidateProfileSerializer
    queryset = CandidateProfile.objects.select_related("user").prefetch_related("skills")

    def get_queryset(self):
        user = self.request.user
        companies = list(user.companies)
        return (
            super()
            .get_queryset()
            .filter(
                Q(user=user) | Q(applications__job__company__in=companies)
            )
            .distinct()
        )

    @action(detail=False, methods=["get", "put", "patch"], url_path="me")
    def me(self, request):
        profile = CandidateProfile.objects.filter(user=request.user).first()
        if request.method == "GET":
            if profile is None:
                return Response(
                    {"detail": "No candidate profile."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(self.get_serializer(profile).data)

        serializer = self.get_serializer(
            profile, data=request.data, partial=request.method == "PATCH"
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data)


class ApplicationViewSet(CompanyScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    permission_classes = [IsCompanyMember]
    queryset = Application.objects.select_related(
        "job", "candidate__user", "current_stage"
    ).prefetch_related("reviews")
    company_field = "job__company"

    def get_queryset(self):
        qs = super().get_queryset()
        job_id = self.request.query_params.get("job")
        if job_id:
            qs = qs.filter(job_id=job_id)
        app_status = self.request.query_params.get("status")
        if app_status:
            qs = qs.filter(status=app_status)
        return qs

    def _require_recruiter(self):
        role = self.request.user.role_in(self.company)
        if role not in (Membership.OWNER, Membership.RECRUITER):
            raise PermissionDenied("Recruiter or owner role required.")

    @action(detail=True, methods=["post"])
    def advance(self, request, pk=None):
        self._require_recruiter()
        application = self.get_object()
        if application.status != Application.ACTIVE:
            raise ValidationError("Only active applications can be advanced.")
        application.advance()
        application.refresh_from_db()
        return Response(self.get_serializer(application).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        self._require_recruiter()
        application = self.get_object()
        application.reject()
        application.refresh_from_db()
        return Response(self.get_serializer(application).data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsInterviewer],
        serializer_class=ApplicationReviewSerializer,
    )
    def review(self, request, pk=None):
        application = self.get_object()
        serializer = ApplicationReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stage = data.get("stage") or application.current_stage
        if stage is None:
            raise ValidationError("The application has no current stage to review.")
        if stage.job_id != application.job_id:
            raise ValidationError("Stage does not belong to this application's job.")
        review, _ = StageReview.objects.update_or_create(
            application=application,
            stage=stage,
            reviewer=request.user,
            defaults={
                "decision": data["decision"],
                "rating": data.get("rating"),
                "feedback": data.get("feedback", ""),
            },
        )
        return Response(
            StageReviewSerializer(review).data, status=status.HTTP_201_CREATED
        )


class StageReviewViewSet(CompanyScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = StageReviewSerializer
    permission_classes = [IsInterviewer]
    queryset = StageReview.objects.select_related("application", "stage", "reviewer")
    company_field = "application__job__company"

    def get_queryset(self):
        qs = super().get_queryset()
        application_id = self.request.query_params.get("application")
        if application_id:
            qs = qs.filter(application_id=application_id)
        return qs


class QuestionViewSet(CompanyScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [IsRecruiterOrOwner]
    queryset = Question.objects.select_related("skill")

    def get_queryset(self):
        qs = super().get_queryset()
        skill_id = self.request.query_params.get("skill")
        if skill_id:
            qs = qs.filter(skill_id=skill_id)
        return qs


class AssessmentViewSet(CompanyScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = AssessmentSerializer
    permission_classes = [IsRecruiterOrOwner]
    queryset = Assessment.objects.select_related("job", "stage").prefetch_related(
        "questions"
    )
    company_field = "job__company"


class AttemptViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Attempts are created via ``start`` and graded via ``submit``.

    Candidates see their own attempts; company members see the attempts on
    their own jobs.
    """

    serializer_class = AttemptSerializer
    queryset = Attempt.objects.select_related("assessment", "application")

    def get_queryset(self):
        user = self.request.user
        companies = list(user.companies)
        return (
            super()
            .get_queryset()
            .filter(
                Q(application__candidate__user=user)
                | Q(application__job__company__in=companies)
            )
            .distinct()
        )

    def _check_access(self, application):
        user = self.request.user
        if getattr(application.candidate, "user_id", None) == user.pk:
            return
        if user.membership_for(application.job.company) is not None:
            return
        raise PermissionDenied("You cannot act on this application.")

    @action(detail=False, methods=["post"], serializer_class=AttemptStartSerializer)
    def start(self, request):
        serializer = AttemptStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assessment = serializer.validated_data["assessment"]
        application = serializer.validated_data["application"]
        self._check_access(application)
        if assessment.job_id != application.job_id:
            raise ValidationError("Assessment does not belong to the application's job.")
        if not assessment.is_active:
            raise ValidationError("This assessment is not active.")
        existing = Attempt.objects.filter(
            assessment=assessment, application=application
        ).first()
        if existing is not None:
            if existing.submitted_at is not None:
                raise ValidationError("This assessment has already been submitted.")
            return Response(AttemptSerializer(existing).data)
        attempt = Attempt.objects.create(
            assessment=assessment, application=application
        )
        return Response(
            AttemptSerializer(attempt).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], serializer_class=AttemptSubmitSerializer)
    def submit(self, request, pk=None):
        attempt = self.get_object()
        self._check_access(attempt.application)
        if attempt.submitted_at is not None:
            raise ValidationError("This attempt has already been submitted.")
        serializer = AttemptSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answers = serializer.validated_data.get("answers")
        if answers is not None:
            attempt.answers = {str(k): v for k, v in answers.items()}
        attempt.submitted_at = timezone.now()
        attempt.save()
        attempt.grade()
        attempt.refresh_from_db()
        return Response(AttemptSerializer(attempt).data)
