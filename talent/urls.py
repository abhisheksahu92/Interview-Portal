from django.urls import path

from talent import views

app_name = "talent"

urlpatterns = [
    path("", views.index, name="index"),
]
