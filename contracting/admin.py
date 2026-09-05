"""Admin registrations for the contracting app (support/debug use only)."""

from django.contrib import admin

from contracting.models import (
    ClientBillingProfile,
    ClientInvoice,
    ClientInvoiceCounter,
    Contractor,
    Engagement,
    OnboardingDocument,
    PayrollRun,
    Timesheet,
)


@admin.register(Contractor)
class ContractorAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "status", "email", "created_at")
    list_filter = ("status", "company")
    search_fields = ("name", "email", "pan", "employee_id")
    # ``bank`` is an encrypted blob; keep it out of the changelist and search.
    exclude = ("bank",)


@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    list_display = (
        "contractor",
        "client",
        "role_title",
        "rate_unit",
        "bill_rate_inr",
        "pay_rate_inr",
        "status",
    )
    list_filter = ("status", "rate_unit")
    search_fields = ("contractor__name", "client__name", "role_title", "po_number")


@admin.register(OnboardingDocument)
class OnboardingDocumentAdmin(admin.ModelAdmin):
    list_display = ("contractor", "kind", "verified_at", "created_at")
    list_filter = ("kind",)


@admin.register(Timesheet)
class TimesheetAdmin(admin.ModelAdmin):
    list_display = ("engagement", "period_start", "period_end", "total_hours", "status")
    list_filter = ("status",)


@admin.register(ClientInvoice)
class ClientInvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "client", "period_start", "total", "status", "due_at")
    list_filter = ("status",)
    search_fields = ("number", "client__name")


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ("company", "month", "gross_total", "tds_total", "net_total", "status")
    list_filter = ("status",)


admin.site.register(ClientBillingProfile)
admin.site.register(ClientInvoiceCounter)
