from django.contrib import admin

from assessments.models import Assessment, Attempt, Question


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "skill", "kind", "difficulty", "source", "created_at")
    list_filter = ("company", "kind", "difficulty", "source")
    search_fields = ("text",)


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "job", "stage", "time_limit_minutes", "pass_mark_percent", "is_active")
    list_filter = ("is_active", "job__company")
    filter_horizontal = ("questions",)
    search_fields = ("title",)


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "assessment", "application", "started_at", "submitted_at", "score_percent", "passed")
    list_filter = ("passed", "assessment__job__company")
