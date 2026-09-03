"""Admin registrations for the partners app."""

from django.contrib import admin

from partners.models import CommissionLedger, License, Referral, Reseller, WhiteLabel


@admin.register(Reseller)
class ResellerAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "commission_pct", "active")
    search_fields = ("name", "code", "contact_email")
    list_filter = ("active",)


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("company", "reseller", "signed_up_at", "first_payment_at")
    list_select_related = ("company", "reseller")


@admin.register(CommissionLedger)
class CommissionLedgerAdmin(admin.ModelAdmin):
    list_display = ("reseller", "company", "invoice_ref", "amount_inr", "commission_inr", "paid_out_at")
    list_select_related = ("company", "reseller")
    search_fields = ("invoice_ref",)


@admin.register(WhiteLabel)
class WhiteLabelAdmin(admin.ModelAdmin):
    list_display = ("company", "brand_name", "custom_domain", "hide_powered_by")


@admin.register(License)
class LicenseAdmin(admin.ModelAdmin):
    list_display = ("company", "kind", "seats", "expires_at", "issued_at")
    search_fields = ("key",)
