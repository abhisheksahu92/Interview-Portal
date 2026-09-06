from django.contrib import admin

from seeker.models import Outreach, SavedItem, SeekerProfile


@admin.register(SeekerProfile)
class SeekerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "mailbox_kind",
        "mailbox_email",
        "is_pro",
        "sends_this_month",
        "month_key",
    )
    list_filter = ("mailbox_kind", "is_pro")
    search_fields = ("user__email", "mailbox_email")
    raw_id_fields = ("user",)
    # mailbox_config is a Fernet token; showing it would only invite pasting.
    exclude = ("mailbox_config",)


@admin.register(SavedItem)
class SavedItemAdmin(admin.ModelAdmin):
    list_display = ("id", "seeker", "title", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("seeker__user__email", "note")
    raw_id_fields = ("seeker", "lead", "job")


@admin.register(Outreach)
class OutreachAdmin(admin.ModelAdmin):
    list_display = ("id", "seeker", "to_email", "subject", "status", "sent_at")
    list_filter = ("status",)
    search_fields = ("to_email", "subject", "seeker__user__email")
    raw_id_fields = ("seeker", "saved_item")
