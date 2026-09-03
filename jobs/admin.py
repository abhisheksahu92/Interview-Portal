from django.contrib import admin

from .models import (
    Application,
    CandidateProfile,
    Job,
    PipelineStage,
    Skill,
    StageReview,
)


class PipelineStageInline(admin.TabularInline):
    model = PipelineStage
    extra = 0


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ["name", "company"]
    list_filter = ["company"]
    search_fields = ["name"]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "status", "employment_type", "created_at"]
    list_filter = ["company", "status", "employment_type"]
    search_fields = ["title", "location"]
    inlines = [PipelineStageInline]
    filter_horizontal = ["skills"]


@admin.register(PipelineStage)
class PipelineStageAdmin(admin.ModelAdmin):
    list_display = ["name", "job", "order", "kind", "requires_assessment"]
    list_filter = ["kind", "requires_assessment"]


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "headline", "experience_years", "notice_period_days"]
    search_fields = ["user__email", "headline"]
    filter_horizontal = ["skills"]


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["candidate", "job", "current_stage", "status", "ai_fit_score"]
    list_filter = ["status", "job__company"]


@admin.register(StageReview)
class StageReviewAdmin(admin.ModelAdmin):
    list_display = ["application", "stage", "reviewer", "decision", "rating"]
    list_filter = ["decision"]
