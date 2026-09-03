from django.urls import path

from partners import views

app_name = "partners"

urlpatterns = [
    path("", views.settings_view, name="settings"),
    path("license/verify/", views.verify_license_view, name="verify_license"),
    path("r/<slug:code>/", views.referral_link, name="referral_link"),
    path("<slug:code>/dashboard/", views.reseller_dashboard, name="reseller_dashboard"),
]
