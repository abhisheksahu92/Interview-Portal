from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from core import cron
from core import views as core_views


def healthz(request):
    """Liveness probe: no auth, no tenant, no database."""
    return HttpResponse("ok")


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("internal/cron/tick/", cron.tick, name="cron_tick"),
    path("admin/", admin.site.urls),
    path("accounts/", include("core.urls")),
    path("jobs/", include("jobs.urls")),
    path("assessments/", include("assessments.urls")),
    path("api/", include("api.urls")),
    path("billing/", include("billing.urls")),
    path("scheduling/", include("scheduling.urls")),
    path("clients/", include("clients.urls")),
    path("notifications/", include("notifications.urls")),
    path("talent/", include("talent.urls")),
    path("video/", include("video.urls")),
    path("careers/", include("careers.urls")),
    path("analytics/", include("analytics.urls")),
    path("offers/", include("offers.urls")),
    path("partners/", include("partners.urls")),
    path("marketplace/", include("marketplace.urls")),
    path("contracting/", include("contracting.urls")),
    path("exchange/", include("exchange.urls")),
    path("integrations/", include("integrations.urls")),
    path("bgv/", include("bgv.urls")),
    path("benchmarks/", include("benchmarks.urls")),
    path("portal/opportunities/", include("seeker.urls")),
    path("jobs/board/", include("board.urls")),
    path("robots.txt", core_views.robots_txt, name="robots_txt"),
    path("sitemap.xml", core_views.sitemap_xml, name="sitemap_xml"),
    path("sitemap-pages.xml", core_views.sitemap_pages_xml, name="sitemap_pages_xml"),
    path("", include("web.urls")),
]

#: 403s render plan-aware copy — see ``core.views.permission_denied``.
handler403 = "core.views.permission_denied"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
