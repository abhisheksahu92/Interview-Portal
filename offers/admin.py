"""Admin registrations for the offers app."""

from django.contrib import admin

from offers.models import Offer, OfferEvent, OfferTemplate


@admin.register(OfferTemplate)
class OfferTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "is_default", "updated_at")
    list_filter = ("company", "is_default")
    search_fields = ("name", "subject")


class OfferEventInline(admin.TabularInline):
    model = OfferEvent
    extra = 0
    readonly_fields = ("kind", "at", "meta")


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("pk", "application", "status", "salary", "currency", "expires_at")
    list_filter = ("status", "currency")
    search_fields = ("application__candidate__user__email", "application__job__title")
    readonly_fields = ("sign_token", "signed_at", "signed_ip", "signed_user_agent")
    inlines = [OfferEventInline]
