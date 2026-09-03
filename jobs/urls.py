"""The ``jobs`` app is domain-only: models, services and the admin.

All server-rendered job/skill/stage screens live in the ``web`` app (the
canonical UI, mounted at ``/`` — see ``web/urls.py``), so this URLconf is
intentionally empty and kept only so the root URLconf include stays stable.
"""

app_name = "jobs"

urlpatterns: list = []
