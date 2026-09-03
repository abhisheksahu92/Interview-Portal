from django.urls import path

from notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.index, name="settings"),
    path("toggle/<str:event>/<str:channel>/", views.toggle, name="toggle"),
    path("test-send/", views.test_send, name="test_send"),
    path("outbox/", views.outbox, name="outbox"),
    path("outbox/<int:pk>/resend/", views.resend, name="resend"),
    path("unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
    path("whatsapp/webhook/", views.whatsapp_webhook, name="whatsapp_webhook"),
]
