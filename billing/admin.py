from django.contrib import admin

from billing.models import (
    DunningReminder,
    Invoice,
    PlacementFee,
    Plan,
    Subscription,
    UsageRecord,
)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "name",
        "max_open_jobs",
        "max_seats",
        "price_monthly_inr",
        "price_yearly_inr",
        "ai_credits_monthly",
    ]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "company",
        "plan",
        "provider",
        "interval",
        "status",
        "trial_ends_at",
        "current_period_end",
    ]
    list_filter = ["status", "plan", "provider", "interval"]
    search_fields = ["company__name", "stripe_customer_id", "stripe_subscription_id"]


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ["company", "kind", "quantity", "period_start", "created_at"]
    list_filter = ["kind", "period_start"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["number", "company", "amount", "total", "issued_at", "paid_at"]
    list_filter = ["fy", "provider"]
    search_fields = ["number", "company__name", "provider_ref", "gstin"]


@admin.register(PlacementFee)
class PlacementFeeAdmin(admin.ModelAdmin):
    list_display = ["company", "application", "amount", "status", "created_at"]
    list_filter = ["status"]


@admin.register(DunningReminder)
class DunningReminderAdmin(admin.ModelAdmin):
    list_display = ["subscription", "day", "sent_at"]
