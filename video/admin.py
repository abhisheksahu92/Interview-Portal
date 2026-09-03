"""Admin registrations for the video app."""

from django.contrib import admin

from video.models import (
    VideoInvite,
    VideoQuestion,
    VideoResponse,
    VideoScreen,
    VideoScreenQuestion,
)


@admin.register(VideoQuestion)
class VideoQuestionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "company", "think_seconds", "answer_seconds", "order")
    list_filter = ("company",)
    search_fields = ("text",)


class VideoScreenQuestionInline(admin.TabularInline):
    model = VideoScreenQuestion
    extra = 1


@admin.register(VideoScreen)
class VideoScreenAdmin(admin.ModelAdmin):
    list_display = ("title", "job", "stage", "deadline_days", "is_active")
    list_filter = ("is_active",)
    inlines = [VideoScreenQuestionInline]


@admin.register(VideoInvite)
class VideoInviteAdmin(admin.ModelAdmin):
    list_display = ("application", "screen", "status", "expires_at", "submitted_at")
    list_filter = ("status",)


@admin.register(VideoResponse)
class VideoResponseAdmin(admin.ModelAdmin):
    list_display = ("invite", "question", "duration_seconds", "status", "ai_score")
    list_filter = ("status",)
