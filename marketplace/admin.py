"""Admin registrations for the marketplace app."""

from django.contrib import admin

from marketplace.models import PackPurchase, QuestionPack


@admin.register(QuestionPack)
class QuestionPackAdmin(admin.ModelAdmin):
    list_display = ("title", "skill_name", "price_inr", "published", "downloads")
    list_filter = ("published", "skill_name")
    search_fields = ("title", "skill_name", "description")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(PackPurchase)
class PackPurchaseAdmin(admin.ModelAdmin):
    list_display = ("company", "pack", "invoice_ref", "purchased_at", "questions_created")
    list_select_related = ("company", "pack")
