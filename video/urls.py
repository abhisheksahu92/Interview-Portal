from django.urls import path

from video import views

app_name = "video"

urlpatterns = [
    path("", views.index, name="index"),
    # Question library
    path("questions/", views.question_list, name="question_list"),
    path("questions/new/", views.question_create, name="question_create"),
    path("questions/<int:pk>/edit/", views.question_edit, name="question_edit"),
    path("questions/<int:pk>/delete/", views.question_delete, name="question_delete"),
    # Screens per job
    path("jobs/<int:job_id>/screens/", views.job_screens, name="job_screens"),
    path("jobs/<int:job_id>/screens/new/", views.screen_create, name="screen_create"),
    path("screens/<int:pk>/edit/", views.screen_edit, name="screen_edit"),
    path("screens/<int:pk>/delete/", views.screen_delete, name="screen_delete"),
    path(
        "screens/<int:screen_id>/invite/<int:application_id>/",
        views.invite_create,
        name="invite_create",
    ),
    # Invites + review
    path("invites/", views.invite_list, name="invite_list"),
    path("invites/<int:pk>/", views.invite_review, name="invite_review"),
    path("responses/<int:pk>/stream/", views.response_stream, name="response_stream"),
    # Candidate recorder (token)
    path("take/<str:token>/", views.take, name="take"),
    path("take/<str:token>/upload/", views.take_upload, name="take_upload"),
    path("take/<str:token>/submit/", views.take_submit, name="take_submit"),
    path("take/<str:token>/done/", views.take_done, name="take_done"),
]
