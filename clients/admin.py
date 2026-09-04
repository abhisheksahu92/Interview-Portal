"""Admin registrations for the clients app."""

from django.contrib import admin

from clients.models import Client, ClientAccess, Submission


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "contact_email", "created_at")
    list_filter = ("company",)
    search_fields = ("name", "contact_email", "contact_name")


@admin.register(ClientAccess)
class ClientAccessAdmin(admin.ModelAdmin):
    list_display = ("email", "client", "expires_at", "revoked_at", "last_used_at")
    list_filter = ("client__company",)
    search_fields = ("email", "client__name")
    readonly_fields = ("token", "last_used_at")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("application", "client", "status", "client_rating", "created_at")
    list_filter = ("status", "client__company")
    search_fields = ("client__name", "application__candidate__user__email")
