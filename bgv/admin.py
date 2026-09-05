from django.contrib import admin

from bgv.models import CheckPackage, VerificationOrder


@admin.register(CheckPackage)
class CheckPackageAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "price_inr", "provider_cost_inr", "margin_inr", "active")
    list_filter = ("active",)
    search_fields = ("code", "name")


@admin.register(VerificationOrder)
class VerificationOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "candidate", "package", "status", "price_inr", "charge_ref")
    list_filter = ("status", "company")
    search_fields = ("provider_ref", "charge_ref", "candidate__user__email")
    raw_id_fields = ("company", "candidate", "application", "ordered_by")
