"""URLs for background verification.

Three audiences: the recruiter workspace (login + role + ``bgv`` entitlement),
the candidate's tokenised consent page (no login — the token is the credential),
and the vendor's webhook (no session, HMAC-signed).
"""

from django.urls import path

from . import views

app_name = "bgv"

urlpatterns = [
    path("", views.index, name="index"),
    path("order/<int:application_id>/", views.order_create, name="order_create"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/cancel/", views.order_cancel, name="order_cancel"),
    path("orders/<int:pk>/report/", views.order_report, name="order_report"),
    path("orders/<int:pk>/refresh/", views.order_refresh, name="order_refresh"),
    path("admin-margin/", views.admin_margin, name="admin_margin"),
    path("consent/<str:token>/", views.consent, name="consent"),
    path("webhook/", views.webhook, name="webhook"),
]
