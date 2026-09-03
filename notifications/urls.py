from django.urls import path

from notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.index, name="settings"),
]
