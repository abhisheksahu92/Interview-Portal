from django.urls import path

from integrations import views

app_name = "integrations"

urlpatterns = [
    path("", views.index, name="index"),
    path("webhooks/new/", views.webhook_create, name="webhook_create"),
    path("webhooks/<int:pk>/edit/", views.webhook_edit, name="webhook_edit"),
    path("webhooks/<int:pk>/delete/", views.webhook_delete, name="webhook_delete"),
    path("webhooks/<int:pk>/test/", views.webhook_test, name="webhook_test"),
    path("webhooks/<int:pk>/rotate/", views.webhook_rotate, name="webhook_rotate"),
    path("deliveries/", views.deliveries, name="deliveries"),
    path("deliveries/<int:pk>/redeliver/", views.delivery_redeliver, name="delivery_redeliver"),
    path("connectors/", views.connectors, name="connectors"),
    path("connectors/<str:kind>/", views.connector_edit, name="connector_edit"),
    path("connectors/<str:kind>/test/", views.connector_test, name="connector_test"),
    path("api-keys/", views.api_keys, name="api_keys"),
    path("api-keys/issue/", views.api_key_issue, name="api_key_issue"),
    path("api-keys/revoke/", views.api_key_revoke, name="api_key_revoke"),
]
