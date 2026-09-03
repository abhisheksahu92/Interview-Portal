from django.urls import path

from analytics import views

app_name = "analytics"

urlpatterns = [
    path("", views.index, name="index"),
    path("charts/", views.charts, name="charts"),
    path("report/", views.monthly_report, name="report"),
    path("metrics/<slug:slug>.json", views.metric_json, name="metric_json"),
    path("export/<slug:slug>.csv", views.export_csv, name="export_csv"),
]
