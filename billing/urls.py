from django.urls import path

from billing import views

app_name = "billing"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("details/", views.billing_details, name="details"),
    path("checkout/", views.checkout, name="checkout"),
    path("portal/", views.portal, name="portal"),
    path("webhook/", views.webhook, name="webhook"),
    path("razorpay/checkout/", views.razorpay_checkout, name="razorpay_checkout"),
    path("razorpay/verify/", views.razorpay_verify, name="razorpay_verify"),
    path("razorpay/webhook/", views.razorpay_webhook, name="razorpay_webhook"),
    path("invoices/<int:pk>/", views.invoice_download, name="invoice_download"),
]
