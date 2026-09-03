"""Notifications: one entrypoint (``notifications.send``) over email/WhatsApp/SMS.

Imported lazily so importing this package never touches models at app-load time.
"""

__all__ = ["send", "effective_channels", "render_all", "set_preference"]


def __getattr__(name):
    if name in __all__:
        from notifications import api

        return getattr(api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
