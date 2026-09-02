from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"
    verbose_name = "Billing"

    def ready(self):
        from billing import signals  # noqa: F401  (registers the pre_save job guard)
