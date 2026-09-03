from django.urls import path

from clients import views

app_name = "clients"

urlpatterns = [
    # Recruiter screens (feature-gated on client_portal)
    path("", views.index, name="index"),
    path("new/", views.create, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/edit/", views.edit, name="edit"),
    path("<int:pk>/access/", views.access_create, name="access_create"),
    path("<int:pk>/access/<int:access_id>/revoke/", views.access_revoke, name="access_revoke"),
    path("<int:pk>/access/<int:access_id>/resend/", views.access_resend, name="access_resend"),
    path(
        "submit/<int:application_id>/",
        views.submit_application,
        name="submit_application",
    ),
    path("submissions/<int:pk>/", views.submission_detail, name="submission_detail"),
    path("jobs/<int:job_id>/client/", views.job_client, name="job_client"),
    # Client portal (token authenticated, no login)
    path("portal/<str:token>/", views.portal, name="portal"),
    path(
        "portal/<str:token>/resume/<int:submission_id>/",
        views.portal_resume,
        name="portal_resume",
    ),
    path(
        "portal/<str:token>/feedback/<int:submission_id>/",
        views.portal_feedback,
        name="portal_feedback",
    ),
]
