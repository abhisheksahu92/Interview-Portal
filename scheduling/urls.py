from django.urls import path

from scheduling import views

app_name = "scheduling"

urlpatterns = [
    # Recruiter
    path("", views.index, name="index"),
    path(
        "applications/<int:pk>/schedule/",
        views.application_schedule,
        name="application_schedule",
    ),
    path(
        "applications/<int:pk>/interviews/",
        views.application_interviews_partial,
        name="application_interviews",
    ),
    path("interviews/<int:pk>/cancel/", views.interview_cancel, name="interview_cancel"),
    path("interviews/<int:pk>/ics/", views.interview_ics_download, name="interview_ics"),
    # Interviewer
    path("availability/", views.availability, name="availability"),
    path(
        "availability/<int:pk>/delete/",
        views.availability_delete,
        name="availability_delete",
    ),
    path("calendars/<str:provider>/connect/", views.oauth_start, name="oauth_start"),
    path("calendars/<str:provider>/callback/", views.oauth_callback, name="oauth_callback"),
    path(
        "calendars/<int:pk>/disconnect/",
        views.calendar_disconnect,
        name="calendar_disconnect",
    ),
    # Candidate (token-authenticated, not feature-gated)
    path("book/<str:token>/", views.book, name="book"),
    path("book/<str:token>/confirm/", views.book_confirm, name="book_confirm"),
    path("book/<str:token>/cancel/", views.book_cancel, name="book_cancel"),
    path("book/<str:token>/done/", views.booked, name="booked"),
    path("book/<str:token>/calendar.ics", views.book_ics, name="book_ics"),
]
