from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def healthz(request):
    """Liveness probe: no auth, no tenant, no database."""
    return HttpResponse("ok")


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("accounts/", include("core.urls")),
    path("jobs/", include("jobs.urls")),
    path("assessments/", include("assessments.urls")),
    path("api/", include("api.urls")),
    path("billing/", include("billing.urls")),
    path("", include("web.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
