"""Admin registrations for the talent app."""

from django.contrib import admin

from talent.models import ImportBatch, TalentProfile


@admin.register(TalentProfile)
class TalentProfileAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "company", "source", "experience_years", "updated_at")
    list_filter = ("company", "source")
    search_fields = ("email", "name", "phone", "headline")
    autocomplete_fields = ()
    filter_horizontal = ("skills",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "status", "total", "created", "updated", "skipped",
                    "created_at")
    list_filter = ("company", "status")
    readonly_fields = ("created_at",)
