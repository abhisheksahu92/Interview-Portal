"""ViewSets for the v1 API. Everything is scoped to the resolved company."""

import csv
from datetime import datetime, time

from django.db.models import Q
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from api.mixins import CompanyScopedViewSetMixin
from api.permissions import (
    HasApiFeature,
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
    InterviewSerializer,
    JobSerializer,
    MembershipSerializer,
    OfferSerializer,
    OutboundWebhookSerializer,
    PipelineStageSerializer,
    QuestionSerializer,
    SkillSerializer,
    StageReviewSerializer,
    SubmissionSerializer,
    TalentProfileSerializer,
    VideoInviteSerializer,
)
from assessments.models import Assessment, Attempt, Question
from clients.models import Submission
from core.models import Company, Membership
from integrations.models import OutboundWebhook
from jobs.models import (
    Application,
    CandidateProfile,
    Job,
    PipelineStage,
    Skill,
    StageReview,
)
from offers.models import Offer
from scheduling.models import Interview
from talent.models import TalentProfile
from video.models import VideoInvite


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


# --- Phase 3 endpoints ---------------------------------------------------
# Every viewset below is gated by ``HasApiFeature`` in addition to the usual
# role permission, so the whole integration surface switches off in one place
# for companies without the ``api`` entitlement.


class Phase3ViewSetMixin(CompanyScopedViewSetMixin):
    """Company scoping plus the ``api`` entitlement gate."""

    permission_classes = [HasApiFeature, IsRecruiterOrOwner]


class InterviewViewSet(
    Phase3ViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only interview feed for calendar/BI integrations."""

    serializer_class = InterviewSerializer
    queryset = Interview.objects.select_related(
        "application__job", "application__candidate__user", "stage"
    ).prefetch_related("interviewers")

    def get_queryset(self):
        qs = super().get_queryset()
        interview_status = self.request.query_params.get("status")
        if interview_status:
            qs = qs.filter(status=interview_status)
        application = self.request.query_params.get("application")
        if application and application.isdigit():
            qs = qs.filter(application_id=int(application))
        return qs


class OfferViewSet(
    Phase3ViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """List/retrieve offers, and stage a DRAFT offer for a human to send."""

    serializer_class = OfferSerializer
    queryset = Offer.objects.select_related(
        "application__job", "application__candidate__user", "template"
    )
    company_field = "application__job__company"

    def get_queryset(self):
        qs = super().get_queryset()
        offer_status = self.request.query_params.get("status")
        if offer_status:
            qs = qs.filter(status=offer_status)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class SubmissionViewSet(
    Phase3ViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only client submissions (staffing firms' shortlists)."""

    serializer_class = SubmissionSerializer
    queryset = Submission.objects.select_related(
        "client", "application__job", "application__candidate__user"
    )
    company_field = "client__company"

    def get_queryset(self):
        qs = super().get_queryset()
        client = self.request.query_params.get("client")
        if client and client.isdigit():
            qs = qs.filter(client_id=int(client))
        submission_status = self.request.query_params.get("status")
        if submission_status:
            qs = qs.filter(status=submission_status)
        return qs


class VideoInviteViewSet(
    Phase3ViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only one-way video screening invites.

    Tokens are deliberately absent from the payload: they are candidate-facing
    credentials, and an API consumer has no reason to impersonate a candidate.
    """

    serializer_class = VideoInviteSerializer
    queryset = VideoInvite.objects.select_related(
        "screen", "application__job", "application__candidate__user"
    )
    company_field = "application__job__company"

    def get_queryset(self):
        qs = super().get_queryset()
        invite_status = self.request.query_params.get("status")
        if invite_status:
            qs = qs.filter(status=invite_status)
        return qs


class TalentProfileViewSet(
    Phase3ViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Talent CRM: read the pool, and push new candidates into it."""

    serializer_class = TalentProfileSerializer
    queryset = TalentProfile.objects.prefetch_related("skills")

    def get_queryset(self):
        qs = super().get_queryset()
        query = self.request.query_params.get("q")
        if query:
            qs = qs.filter(
                Q(name__icontains=query)
                | Q(email__icontains=query)
                | Q(headline__icontains=query)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class OutboundWebhookViewSet(Phase3ViewSetMixin, viewsets.ModelViewSet):
    """Full CRUD over the company's outbound webhooks.

    The plaintext signing secret is returned exactly once, in the create
    response; every later read shows a masked hint.
    """

    serializer_class = OutboundWebhookSerializer
    queryset = OutboundWebhook.objects.select_related("company")

    def perform_create(self, serializer):
        serializer._reveal_secret = True
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="test")
    def send_test(self, request, pk=None):
        """Deliver a synthetic payload so a receiver can be verified."""
        from integrations.delivery import send_test_event

        webhook = self.get_object()
        delivery = send_test_event(webhook)
        return Response(
            {
                "delivery_id": delivery.pk,
                "status": delivery.status,
                "response_code": delivery.response_code,
                "error": delivery.last_error or None,
            }
        )


@extend_schema(
    summary="Hires export (CSV)",
    description=(
        "One row per hired application in the window, with the accepted offer's "
        "salary and joining date. Streamed as text/csv for payroll import."
    ),
    parameters=[
        OpenApiParameter(
            "from",
            OpenApiTypes.DATE,
            description="Only hires updated on or after this date (YYYY-MM-DD).",
        ),
        OpenApiParameter(
            "to",
            OpenApiTypes.DATE,
            description="Only hires updated on or before this date, inclusive.",
        ),
    ],
    responses={(200, "text/csv"): OpenApiTypes.STR},
)
class HiresExportView(APIView):
    """``GET /api/v1/exports/hires.csv?from=&to=`` — streaming payroll export.

    One row per hired application in the window, with the accepted offer's
    salary and joining date where there is one, so payroll can be reconciled
    without a database dump. Streamed row-by-row: a busy agency's full history
    must not be buffered in memory.

    ``from``/``to`` are ``YYYY-MM-DD`` dates compared against the application's
    last update (the moment it became HIRED); ``to`` is inclusive.
    """

    permission_classes = [HasApiFeature, IsRecruiterOrOwner]
    #: an APIView has no queryset, but the scoping mixin's company resolution
    #: is exactly what we need, so borrow it via composition.
    company_field = "job__company"

    HEADER = [
        "application_id",
        "candidate_name",
        "candidate_email",
        "candidate_phone",
        "job_title",
        "job_location",
        "employment_type",
        "client",
        "hired_on",
        "offer_status",
        "salary",
        "currency",
        "joining_date",
    ]

    @property
    def company(self):
        if not hasattr(self, "_company"):
            self._company = self._resolve_company()
        return self._company

    def _resolve_company(self):
        helper = CompanyScopedViewSetMixin()
        helper.request = self.request
        return helper.resolve_company()

    def _parse_date(self, raw, end=False):
        if not raw:
            return None
        parsed = parse_date(raw.strip())
        if parsed is None:
            raise ValidationError(
                {"detail": f"Invalid date '{raw}'. Use YYYY-MM-DD."}
            )
        moment = datetime.combine(
            parsed, time.max if end else time.min
        )
        return timezone.make_aware(moment) if timezone.is_naive(moment) else moment

    def get_queryset(self):
        company = self.company
        if company is None:
            return Application.objects.none()
        qs = (
            Application.objects.filter(
                job__company=company, status=Application.HIRED
            )
            .select_related("job", "job__client", "candidate__user")
            .prefetch_related("offers")
            .order_by("updated_at", "pk")
        )
        start = self._parse_date(self.request.query_params.get("from"))
        end = self._parse_date(self.request.query_params.get("to"), end=True)
        if start:
            qs = qs.filter(updated_at__gte=start)
        if end:
            qs = qs.filter(updated_at__lte=end)
        return qs

    def rows(self, queryset):
        writer = csv.writer(Echo())
        yield writer.writerow(self.HEADER)
        for application in queryset.iterator(chunk_size=200):
            yield writer.writerow(self.row_for(application))

    @staticmethod
    def row_for(application):
        user = getattr(application.candidate, "user", None)
        offer = next(
            (o for o in application.offers.all() if o.status == "ACCEPTED"),
            None,
        )
        client = getattr(application.job, "client", None)
        return [
            application.pk,
            (user.get_full_name() if user else "") or "",
            getattr(user, "email", "") or "",
            application.candidate.phone or "",
            application.job.title,
            application.job.location or "",
            application.job.employment_type,
            getattr(client, "name", "") or "",
            application.updated_at.date().isoformat(),
            offer.status if offer else "",
            str(offer.salary) if offer else "",
            offer.currency if offer else "",
            offer.joining_date.isoformat() if offer and offer.joining_date else "",
        ]

    def get(self, request):
        response = StreamingHttpResponse(
            self.rows(self.get_queryset()), content_type="text/csv"
        )
        response["Content-Disposition"] = 'attachment; filename="hires.csv"'
        return response


class Echo:
    """A write-only file-like object handing each written row straight back."""

    def write(self, value):
        return value
