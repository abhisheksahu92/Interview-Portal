"""URLs for the contracting app.

Three groups: the recruiter workspace (login + role + feature gate), the
contractor's tokenised self-service pages under ``t/``, and the POST endpoints
the client portal's timesheet panel posts to under ``portal/``.
"""

from django.urls import path

from . import views

app_name = "contracting"

urlpatterns = [
    path("", views.index, name="index"),
    # Contractors
    path("contractors/", views.contractor_list, name="contractor_list"),
    path("contractors/new/", views.contractor_create, name="contractor_create"),
    path("contractors/<int:pk>/", views.contractor_detail, name="contractor_detail"),
    path("contractors/<int:pk>/edit/", views.contractor_edit, name="contractor_edit"),
    path("contractors/<int:pk>/documents/", views.document_upload, name="document_upload"),
    path(
        "contractors/<int:pk>/documents/<int:document_id>/verify/",
        views.document_verify,
        name="document_verify",
    ),
    path(
        "contractors/<int:pk>/rotate-link/",
        views.contractor_rotate_link,
        name="contractor_rotate_link",
    ),
    # Engagements
    path("engagements/", views.engagement_list, name="engagement_list"),
    path(
        "contractors/<int:contractor_id>/engagements/new/",
        views.engagement_create,
        name="engagement_create",
    ),
    path("engagements/<int:pk>/edit/", views.engagement_edit, name="engagement_edit"),
    # Timesheets
    path("timesheets/", views.timesheet_queue, name="timesheet_queue"),
    path(
        "timesheets/<int:pk>/<slug:decision>/",
        views.timesheet_decide,
        name="timesheet_decide",
    ),
    # Client invoices
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/generate/", views.invoice_generate, name="invoice_generate"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<int:pk>/send/", views.invoice_send, name="invoice_send"),
    path("invoices/<int:pk>/paid/", views.invoice_mark_paid, name="invoice_mark_paid"),
    path("invoices/<int:pk>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("clients/<int:client_id>/billing/", views.billing_profile, name="billing_profile"),
    # Payroll
    path("payroll/", views.payroll_list, name="payroll_list"),
    path("payroll/run/", views.payroll_run, name="payroll_run"),
    path("payroll/<int:pk>/", views.payroll_detail, name="payroll_detail"),
    path("payroll/<int:pk>/csv/", views.payroll_download, name="payroll_download"),
    # Contractor self-service (token in the URL is the credential)
    path("t/<str:token>/", views.contractor_portal, name="contractor_portal"),
    path(
        "t/<str:token>/timesheet/<int:pk>/",
        views.contractor_timesheet,
        name="contractor_timesheet",
    ),
    # Client portal actions (ClientAccess token in the URL)
    path(
        "portal/<str:token>/timesheets/<int:pk>/<slug:decision>/",
        views.portal_timesheet_decide,
        name="portal_timesheet_decide",
    ),
]
