from django.urls import path

from . import views

app_name = "jobs"

urlpatterns = [
    # Public job board
    path("", views.job_list, name="job_list"),
    path("<int:pk>/", views.job_detail, name="job_detail"),
    path("<int:pk>/apply/", views.job_apply, name="job_apply"),
    path("my/applications/", views.my_applications, name="my_applications"),
    # Recruiter job management
    path("manage/", views.manage_job_list, name="manage_job_list"),
    path("manage/new/", views.manage_job_create, name="manage_job_create"),
    path("manage/<int:pk>/", views.manage_job_detail, name="manage_job_detail"),
    path("manage/<int:pk>/edit/", views.manage_job_edit, name="manage_job_edit"),
    path("manage/<int:pk>/delete/", views.manage_job_delete, name="manage_job_delete"),
    # Pipeline stages
    path("manage/<int:job_pk>/stages/new/", views.stage_create, name="stage_create"),
    path("manage/<int:job_pk>/stages/<int:pk>/edit/", views.stage_edit, name="stage_edit"),
    path(
        "manage/<int:job_pk>/stages/<int:pk>/delete/",
        views.stage_delete,
        name="stage_delete",
    ),
    path("manage/<int:job_pk>/stages/reorder/", views.stage_reorder, name="stage_reorder"),
    # Skills
    path("skills/", views.skill_list, name="skill_list"),
    path("skills/new/", views.skill_create, name="skill_create"),
    path("skills/<int:pk>/edit/", views.skill_edit, name="skill_edit"),
    path("skills/<int:pk>/delete/", views.skill_delete, name="skill_delete"),
]
