from django.urls import path

from assessments import views

app_name = "assessments"

urlpatterns = [
    # Recruiter: question bank
    path("questions/", views.question_list, name="question_list"),
    path("questions/new/", views.question_create, name="question_create"),
    path("questions/<int:pk>/edit/", views.question_edit, name="question_edit"),
    path("questions/<int:pk>/delete/", views.question_delete, name="question_delete"),
    path("questions/generate/", views.question_generate, name="question_generate"),
    # Recruiter: assessment builder
    path("jobs/<int:job_id>/assessments/", views.job_assessments, name="job_assessments"),
    path("jobs/<int:job_id>/assessments/new/", views.assessment_create, name="assessment_create"),
    path("<int:pk>/edit/", views.assessment_edit, name="assessment_edit"),
    path("<int:pk>/attempts/", views.assessment_attempts, name="assessment_attempts"),
    path(
        "attempts/<int:pk>/manual-score/",
        views.attempt_manual_score,
        name="attempt_manual_score",
    ),
    # Candidate
    path(
        "applications/<int:application_id>/take/<int:assessment_id>/",
        views.take_assessment,
        name="take_assessment",
    ),
    path("attempts/<int:pk>/submit/", views.submit_attempt, name="submit_attempt"),
    path("attempts/<int:pk>/result/", views.attempt_result, name="attempt_result"),
]
