"""Scheduled work driven from outside, for hosting that has no cron.

``/internal/cron/tick/?token=...`` runs a bounded slice of the periodic work and
returns a JSON summary. An external uptime monitor calls it every five minutes;
the free tiers of Render, Fly and Railway all lack a scheduler, and a request
that finishes inside the gunicorn timeout is the one thing they do offer.

The maintenance runner (trials, dunning, reminders, webhooks) runs at most every
``MAINTENANCE_EVERY``; source fetching runs every tick within its time budget.
"""

import hmac
import logging
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.models import CronState

logger = logging.getLogger(__name__)

MAINTENANCE_EVERY = timedelta(minutes=30)
MAINTENANCE_KEY = "run_periodic"


def _authorised(request):
    expected = getattr(settings, "CRON_TOKEN", "") or ""
    supplied = request.GET.get("token") or request.headers.get("X-Cron-Token") or ""
    # Blank token disables the endpoint outright rather than accepting blank.
    return bool(expected) and hmac.compare_digest(supplied, expected)


def _maintenance_due(now):
    state, _ = CronState.objects.get_or_create(key=MAINTENANCE_KEY)
    return state, (state.last_run_at is None or now - state.last_run_at >= MAINTENANCE_EVERY)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def tick(request):
    if not _authorised(request):
        return JsonResponse({"error": "unauthorised"}, status=401)

    now = timezone.now()
    summary = {"maintenance": "skipped", "sources": None}

    state, due = _maintenance_due(now)
    if due:
        # Claim the slot first so overlapping ticks do not both run it.
        state.last_run_at = now
        state.save(update_fields=["last_run_at"])
        try:
            call_command("run_periodic", skip=["fetch_sources"], verbosity=0)
            state.last_status = "ok"
            summary["maintenance"] = "ran"
        except Exception as exc:  # the next tick retries; never 500 the monitor
            logger.exception("run_periodic failed inside the cron tick")
            state.last_status = f"error: {exc}"[:200]
            summary["maintenance"] = "error"
        state.save(update_fields=["last_status"])

    try:
        from sources.services import tick as fetch_tick

        summary["sources"] = fetch_tick(
            budget_seconds=getattr(settings, "CRON_TICK_BUDGET_SECONDS", 25)
        )
    except Exception as exc:
        logger.exception("source tick failed")
        summary["sources"] = {"error": str(exc)[:200]}

    return JsonResponse(summary)
