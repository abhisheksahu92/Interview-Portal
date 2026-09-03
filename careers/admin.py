"""Admin registrations for the careers app."""

from django.contrib import admin

from careers.models import CareersSite, JobDistribution


@admin.register(CareersSite)
class CareersSiteAdmin(admin.ModelAdmin):
    list_display = ("slug", "company", "published", "custom_domain")
    list_filter = ("published",)
    search_fields = ("slug", "company__name", "custom_domain")


@admin.register(JobDistribution)
class JobDistributionAdmin(admin.ModelAdmin):
    list_display = ("job", "board", "status", "posted_at")
    list_filter = ("board", "status")
