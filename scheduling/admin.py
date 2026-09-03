"""Admin registrations for the scheduling app."""

from django.contrib import admin

from scheduling.models import (
    CalendarConnection,
    Interview,
    InterviewerAvailability,
    InterviewSlotProposal,
)


@admin.register(InterviewerAvailability)
class InterviewerAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "weekday", "start", "end", "timezone")
    list_filter = ("company", "weekday", "timezone")
    search_fields = ("user__email",)
    autocomplete_fields = ()


@admin.register(CalendarConnection)
class CalendarConnectionAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "enabled", "last_synced")
    list_filter = ("provider", "enabled")
    search_fields = ("user__email", "account_email")


class InterviewSlotProposalInline(admin.TabularInline):
    model = InterviewSlotProposal
    extra = 0


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "application", "status", "scheduled_start", "timezone")
    list_filter = ("company", "status")
    search_fields = ("application__candidate__user__email", "booking_token")
    filter_horizontal = ("interviewers",)
    readonly_fields = ("booking_token", "created_at", "updated_at")
    inlines = [InterviewSlotProposalInline]
