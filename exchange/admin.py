from django.contrib import admin

from exchange.models import ExchangeDeal, ExchangeRequirement, ExchangeSubmission, PartnerLink


@admin.register(PartnerLink)
class PartnerLinkAdmin(admin.ModelAdmin):
    list_display = ("from_company", "to_company", "status", "created_at")
    list_filter = ("status",)


@admin.register(ExchangeRequirement)
class ExchangeRequirementAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "visibility", "status", "fee_split_pct", "expires_at")
    list_filter = ("status", "visibility")
    search_fields = ("title",)


@admin.register(ExchangeSubmission)
class ExchangeSubmissionAdmin(admin.ModelAdmin):
    """Contact details are deliberately not listed here either."""

    list_display = ("reference", "requirement", "responding_company", "status", "revealed_at")
    list_filter = ("status",)


@admin.register(ExchangeDeal)
class ExchangeDealAdmin(admin.ModelAdmin):
    list_display = ("id", "placement_fee_inr", "split_pct", "platform_fee_pct", "status", "disputed")
    list_filter = ("status", "disputed")
