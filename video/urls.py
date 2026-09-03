from django.urls import path

from video import views

app_name = "video"

urlpatterns = [
    path("", views.index, name="index"),
]
