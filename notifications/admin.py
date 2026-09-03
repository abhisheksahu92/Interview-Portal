"""Admin registrations for the notifications app."""

from django.contrib import admin

from notifications.models import (
    CandidateChannelOptOut,
    NotificationPreference,
    OutboundMessage,
)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("company", "event", "channels", "updated_at")
    list_filter = ("event",)
    search_fields = ("event",)


@admin.register(CandidateChannelOptOut)
class CandidateChannelOptOutAdmin(admin.ModelAdmin):
    list_display = ("profile", "channel", "created_at")
    list_filter = ("channel",)


@admin.register(OutboundMessage)
class OutboundMessageAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "event", "channel", "recipient", "status", "attempts", "company",
    )
    list_filter = ("status", "channel", "event")
    search_fields = ("recipient_email", "recipient_phone", "provider_ref", "subject")
    readonly_fields = ("created_at", "sent_at", "last_attempt_at")
