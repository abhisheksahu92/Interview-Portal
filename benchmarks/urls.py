"""URLs for salary benchmarks.

The report, its CSV and its PDF are gated on the ``analytics`` feature and an
OWNER/RECRUITER role. ``public`` is the marketing teaser: no login, no tenant,
and a far stricter anonymity threshold.
"""

from django.urls import path

from . import views

app_name = "benchmarks"

urlpatterns = [
    path("", views.index, name="index"),
    path("export.csv", views.export_csv, name="csv"),
    path("snapshot.pdf", views.export_pdf, name="pdf"),
    path("public/", views.public, name="public"),
]
