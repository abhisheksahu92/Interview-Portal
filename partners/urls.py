from django.urls import path

from partners import views

app_name = "partners"

urlpatterns = [
    path("", views.index, name="settings"),
]
