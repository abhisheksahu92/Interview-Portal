from django.apps import AppConfig


class VideoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "video"
    verbose_name = "Video screening"

    def ready(self):
        from video import signals  # noqa: F401
