"""Public cross-tenant job board."""

from django.urls import path

from board import views
from board.feeds import BoardFeed

app_name = "board"

urlpatterns = [
    path("", views.job_list, name="list"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
    path("feed.xml", BoardFeed(), name="feed"),
    path("network-toggle/", views.network_toggle, name="network_toggle"),
    path("<int:pk>/", views.job_detail, name="job_detail"),
    path("<int:pk>/apply/", views.job_apply, name="job_apply"),
]
