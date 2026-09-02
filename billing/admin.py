from django.contrib import admin

from billing.models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "max_open_jobs", "price_monthly", "stripe_price_id"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["company", "plan", "status", "current_period_end"]
    list_filter = ["status", "plan"]
    search_fields = ["company__name", "stripe_customer_id", "stripe_subscription_id"]
