"""Admin registrations for the partners app (added by the partners agent)."""
from django.apps import AppConfig


class PartnersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "partners"
    verbose_name = "Partners & branding"

    def ready(self):
        from partners import signals  # noqa: F401
