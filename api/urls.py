"""API URLs: /api/v1/ router plus OpenAPI schema and docs."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from api import views

app_name = "api"

router = DefaultRouter()
router.register("companies", views.CompanyViewSet, basename="company")
router.register("memberships", views.MembershipViewSet, basename="membership")
router.register("skills", views.SkillViewSet, basename="skill")
router.register("jobs", views.JobViewSet, basename="job")
router.register("stages", views.PipelineStageViewSet, basename="pipelinestage")
router.register("candidates", views.CandidateProfileViewSet, basename="candidateprofile")
router.register("applications", views.ApplicationViewSet, basename="application")
router.register("reviews", views.StageReviewViewSet, basename="stagereview")
router.register("questions", views.QuestionViewSet, basename="question")
router.register("assessments", views.AssessmentViewSet, basename="assessment")
router.register("attempts", views.AttemptViewSet, basename="attempt")
# --- Phase 3 (feature "api") ---
router.register("interviews", views.InterviewViewSet, basename="interview")
router.register("offers", views.OfferViewSet, basename="offer")
router.register("submissions", views.SubmissionViewSet, basename="submission")
router.register("video-invites", views.VideoInviteViewSet, basename="videoinvite")
router.register("talent", views.TalentProfileViewSet, basename="talentprofile")
router.register("webhooks", views.OutboundWebhookViewSet, basename="outboundwebhook")

urlpatterns = [
    path("v1/", include(router.urls)),
    path("v1/auth/token/", views.AuthTokenView.as_view(), name="auth-token"),
    path(
        "v1/exports/hires.csv",
        views.HiresExportView.as_view(),
        name="export-hires",
    ),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="api:schema"),
        name="docs",
    ),
]
