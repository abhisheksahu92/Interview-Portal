"""URL map for the careers app.

Recruiter settings live at the app root (``careers:index``); everything else is
public. The root view doubles as the custom-domain entry point: when
``request.get_host()`` matches a published site's ``custom_domain`` it renders
that public site instead of the settings page (see ``views.index``).
"""

from django.urls import path

from careers import views

app_name = "careers"

urlpatterns = [
    path("", views.index, name="index"),
    path("preview/", views.preview, name="preview"),
    path("distribute/<int:pk>/", views.job_distribution, name="job_distribution"),
    path("distribute/<int:pk>/<str:board>/", views.distribute_action, name="distribute_action"),
    path("feeds/indeed.xml", views.indeed_feed, name="indeed_feed"),
    path("<slug:slug>/", views.public_site, name="site"),
    path("<slug:slug>/sitemap.xml", views.sitemap, name="sitemap"),
    path("<slug:slug>/jobs/<int:pk>/", views.public_job, name="job_detail"),
]
