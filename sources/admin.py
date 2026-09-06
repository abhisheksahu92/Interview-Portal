from django.contrib import admin, messages

from sources import services
from sources.models import Lead, Source


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "kind", "enabled", "last_run_at", "last_status", "items_seen")
    list_filter = ("kind", "enabled", "last_status")
    search_fields = ("slug", "name")
    readonly_fields = ("last_run_at", "last_status", "last_error", "items_seen", "created_at")
    actions = ["run_now"]

    @admin.action(description="Run now (fetch leads)")
    def run_now(self, request, queryset):
        """Fetch the selected sources synchronously — handy for a new board slug."""
        created = 0
        for source in queryset:
            stats = services.run_source(source)
            created += stats["created"]
            if stats["status"] == Source.ERROR:
                self.message_user(
                    request, f"{source.slug}: {source.last_error}", level=messages.ERROR
                )
        self.message_user(request, f"{created} new lead(s).", level=messages.SUCCESS)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("title", "company_name", "source", "kind", "remote", "posted_at", "is_active")
    list_filter = ("kind", "is_active", "remote", "source")
    search_fields = ("title", "company_name", "snippet", "contact_email")
    raw_id_fields = ("source",)
    readonly_fields = ("content_hash", "fetched_at")
