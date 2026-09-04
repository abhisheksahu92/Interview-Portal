from django.contrib import admin

from integrations.models import (
    ConnectorConfig,
    ConnectorRun,
    OutboundWebhook,
    WebhookDelivery,
)


@admin.register(OutboundWebhook)
class OutboundWebhookAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "url", "active", "created_at")
    list_filter = ("active", "company")
    search_fields = ("name", "url")


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ("event", "webhook", "status", "attempts", "response_code", "created_at")
    list_filter = ("status", "event")


@admin.register(ConnectorConfig)
class ConnectorConfigAdmin(admin.ModelAdmin):
    list_display = ("kind", "company", "active", "updated_at")
    list_filter = ("kind", "active")
    #: never render decrypted credentials in the Django admin.
    exclude = ("settings",)


@admin.register(ConnectorRun)
class ConnectorRunAdmin(admin.ModelAdmin):
    list_display = ("kind", "status", "config", "created_at")
    list_filter = ("kind", "status")
