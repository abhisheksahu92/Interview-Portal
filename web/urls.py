from django.urls import path

from web import views

app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    # recruiter / owner
    path("dashboard/", views.dashboard, name="dashboard"),
    path("workspace/jobs/new/", views.job_create, name="job_create"),
    path("workspace/jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("workspace/jobs/<int:pk>/edit/", views.job_edit, name="job_edit"),
    path("workspace/jobs/<int:pk>/board/", views.job_kanban, name="job_kanban"),
    path("workspace/jobs/<int:pk>/stages/", views.settings_stages, name="settings_stages"),
    path("workspace/stages/<int:pk>/delete/", views.stage_delete, name="stage_delete"),
    path(
        "workspace/applications/<int:pk>/advance/",
        views.application_advance,
        name="application_advance",
    ),
    path(
        "workspace/applications/<int:pk>/reject/",
        views.application_reject,
        name="application_reject",
    ),
    path(
        "workspace/applications/<int:pk>/review/",
        views.application_review,
        name="application_review",
    ),
    path(
        "workspace/candidates/<int:pk>/",
        views.candidate_detail,
        name="candidate_detail",
    ),
    path(
        "workspace/candidates/<int:pk>/resume/",
        views.candidate_resume,
        name="candidate_resume",
    ),
    # interviewer
    path("queue/", views.interviewer_queue, name="interviewer_queue"),
    # company settings
    path("settings/members/", views.settings_members, name="settings_members"),
    path("settings/members/<int:pk>/remove/", views.member_remove, name="member_remove"),
    path(
        "settings/invitations/<int:pk>/resend/",
        views.invite_resend,
        name="invite_resend",
    ),
    path(
        "settings/invitations/<int:pk>/revoke/",
        views.invite_revoke,
        name="invite_revoke",
    ),
    path("settings/skills/", views.settings_skills, name="settings_skills"),
    path("settings/skills/<int:pk>/delete/", views.skill_delete, name="skill_delete"),
    path("workspace/stages/<int:pk>/edit/", views.stage_edit, name="stage_edit"),
    path(
        "workspace/stages/<int:pk>/move/<str:direction>/",
        views.stage_move,
        name="stage_move",
    ),
    path(
        "workspace/applications/<int:pk>/stage/",
        views.application_set_stage,
        name="application_set_stage",
    ),
    path("settings/skills/<int:pk>/edit/", views.skill_edit, name="skill_edit"),
    # candidate portal
    path("portal/", views.candidate_home, name="candidate_home"),
    path("portal/profile/", views.candidate_profile, name="candidate_profile"),
    path("openings/", views.job_browse, name="job_browse"),
    path("openings/<int:pk>/", views.job_public_detail, name="job_public_detail"),
    path("openings/<int:pk>/apply/", views.job_apply, name="job_apply"),
]
