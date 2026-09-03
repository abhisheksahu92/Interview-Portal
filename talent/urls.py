from django.urls import path

from talent import views

app_name = "talent"

urlpatterns = [
    path("", views.index, name="index"),
    path("export/", views.export, name="export"),
    path("actions/", views.bulk_action, name="bulk_action"),
    path("import/", views.import_wizard, name="import"),
    path("import/<int:pk>/", views.batch_report, name="batch_report"),
    path("import/<int:pk>/status/", views.batch_status, name="batch_status"),
    path("new/", views.profile_create, name="profile_create"),
    path("<int:pk>/", views.profile_detail, name="profile_detail"),
    path("<int:pk>/edit/", views.profile_edit, name="profile_edit"),
    path("<int:pk>/resume/", views.profile_resume, name="profile_resume"),
    path("<int:pk>/contacted/", views.profile_contacted, name="profile_contacted"),
]
