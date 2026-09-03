"""Admin registrations for the analytics app."""

from django.contrib import admin

from analytics.models import StageTransition


@admin.register(StageTransition)
class StageTransitionAdmin(admin.ModelAdmin):
    list_display = ("application", "from_stage", "to_stage", "status_after", "at")
    list_filter = ("status_after",)
    date_hierarchy = "at"
    raw_id_fields = ("application", "from_stage", "to_stage")
