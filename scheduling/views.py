"""Views for the scheduling app.

Recruiter/interviewer screens are behind ``billing.entitlements.require_feature
("scheduling")``. The candidate booking page is deliberately *not* gated and not
login-protected: it is authenticated by the interview's ``booking_token``.
"""

import secrets
from datetime import UTC, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST

from billing.entitlements import require_feature
from jobs.models import Application
from scheduling import gateway, services
from scheduling.forms import (
    AvailabilityForm,
    BookingForm,
    CancelBookingForm,
    ProposeInterviewForm,
)
from scheduling.ics import FILENAME, MIMETYPE, interview_ics
from scheduling.models import (
    WEEKDAYS,
    CalendarConnection,
    Interview,
    InterviewerAvailability,
    valid_timezone,
)

OAUTH_STATE_KEY = "scheduling_oauth_state"


def _company(request):
    company = getattr(request, "company", None)
    if company is None:
        raise Http404("No active workspace.")
    return company


# ------------------------------------------------------------ recruiter


@login_required
@require_feature("scheduling")
def index(request):
    """Upcoming interviews plus a calendar-week view for the workspace."""
    company = _company(request)
    upcoming = list(services.upcoming_for_company(company)[:50])
    context = {
        "upcoming": upcoming,
        "week": _week_context(company, request.GET.get("week")),
        "calendar_configured": gateway.configured(),
        "interviewer_count": services.eligible_interviewers(company).count(),
    }
    if request.headers.get("HX-Request") and request.GET.get("week"):
        return render(request, "scheduling/partials/week.html", context)
    return render(request, "scheduling/index.html", context)


def _week_context(company, offset_param=None):
    """Seven-day grid of interviews starting on Monday of the target week."""
    try:
        offset = int(offset_param or 0)
    except (TypeError, ValueError):
        offset = 0
    offset = max(-52, min(52, offset))
    today = dj_timezone.localdate()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    start = datetime.combine(monday, time.min, tzinfo=UTC)
    end = start + timedelta(days=7)
    interviews = (
        Interview.objects.for_company(company)
        .filter(
            scheduled_start__gte=start,
            scheduled_start__lt=end,
            status__in=Interview.OPEN_STATUSES + (Interview.COMPLETED,),
        )
        .select_related("application__job", "application__candidate__user", "stage")
        .prefetch_related("interviewers")
    )
    buckets = {monday + timedelta(days=i): [] for i in range(7)}
    for interview in interviews:
        day = interview.scheduled_start.astimezone(UTC).date()
        buckets.setdefault(day, []).append(interview)
    return {
        "offset": offset,
        "prev": offset - 1,
        "next": offset + 1,
        "monday": monday,
        "sunday": monday + timedelta(days=6),
        "days": [
            {"date": day, "interviews": items, "is_today": day == today}
            for day, items in sorted(buckets.items())
        ],
    }


@login_required
@require_feature("scheduling")
def application_schedule(request, pk):
    """The per-application "Schedule interview" panel."""
    company = _company(request)
    application = get_object_or_404(
        Application.objects.select_related("job", "candidate__user", "current_stage"),
        pk=pk,
        job__company=company,
    )
    form = ProposeInterviewForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        interview = services.propose_interview(
            application,
            list(form.cleaned_data["interviewers"]),
            duration=form.cleaned_data["duration"],
            stage=application.current_stage,
            tz=form.cleaned_data["timezone"],
            created_by=request.user,
            location_or_link=form.cleaned_data["location_or_link"],
            notes=form.cleaned_data["notes"],
        )
        messages.success(
            request,
            "Booking link sent to the candidate. "
            f"They can pick a time at {interview.booking_path()}",
        )
        return redirect("scheduling:application_schedule", pk=application.pk)
    return render(
        request,
        "scheduling/application_schedule.html",
        {
            "application": application,
            "form": form,
            "interviews": services.interviews_for_application(application),
            "eligible_count": services.eligible_interviewers(company).count(),
        },
    )


@login_required
@require_feature("scheduling")
def application_interviews_partial(request, pk):
    """HTMX-friendly fragment: upcoming interviews for one application."""
    company = _company(request)
    application = get_object_or_404(Application, pk=pk, job__company=company)
    return render(
        request,
        "scheduling/partials/application_interviews.html",
        {
            "application": application,
            "interviews": services.interviews_for_application(application),
        },
    )


@login_required
@require_feature("scheduling")
@require_POST
def interview_cancel(request, pk):
    """Recruiter-side cancellation."""
    company = _company(request)
    interview = get_object_or_404(Interview.objects.for_company(company), pk=pk)
    services.cancel(interview, reason=request.POST.get("reason", ""))
    messages.info(request, "Interview cancelled and the candidate notified.")
    target = request.POST.get("next") or reverse("scheduling:index")
    return HttpResponseRedirect(target)


@login_required
@require_feature("scheduling")
def interview_ics_download(request, pk):
    """Download the .ics for one interview."""
    company = _company(request)
    interview = get_object_or_404(Interview.objects.for_company(company), pk=pk)
    payload = interview_ics(interview)
    if not payload:
        raise Http404("This interview has no confirmed time yet.")
    response = HttpResponse(payload, content_type=MIMETYPE)
    response["Content-Disposition"] = f'attachment; filename="{FILENAME}"'
    return response


# ------------------------------------------------------------ interviewer


@login_required
@require_feature("scheduling")
def availability(request):
    """Weekly availability grid editor for the signed-in member."""
    company = _company(request)
    form = AvailabilityForm(request.POST or None, company=company, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Availability window added.")
        return redirect("scheduling:availability")
    windows = InterviewerAvailability.objects.for_company(company).filter(user=request.user)
    by_weekday = {value: [] for value, _ in WEEKDAYS}
    for window in windows:
        by_weekday.setdefault(window.weekday, []).append(window)
    connections = {c.provider: c for c in CalendarConnection.objects.filter(user=request.user)}
    providers = gateway.status()
    for row in providers:
        row["connection"] = connections.get(row["provider"])
    return render(
        request,
        "scheduling/availability.html",
        {
            "form": form,
            "grid": [
                {"weekday": value, "label": label, "windows": by_weekday.get(value, [])}
                for value, label in WEEKDAYS
            ],
            "providers": providers,
        },
    )


@login_required
@require_feature("scheduling")
@require_POST
def availability_delete(request, pk):
    company = _company(request)
    window = get_object_or_404(
        InterviewerAvailability.objects.for_company(company), pk=pk, user=request.user
    )
    window.delete()
    messages.info(request, "Availability window removed.")
    return redirect("scheduling:availability")


# ------------------------------------------------------------ OAuth


def _adapter_or_404(provider):
    from scheduling.calendar import adapter_for

    adapter = adapter_for(provider)
    if adapter is None:
        raise Http404("Unknown calendar provider.")
    return adapter


def _callback_uri(request, provider):
    return request.build_absolute_uri(reverse("scheduling:oauth_callback", args=[provider]))


@login_required
@require_feature("scheduling")
def oauth_start(request, provider):
    """Redirect the user to the provider's consent screen."""
    _company(request)
    adapter = _adapter_or_404(provider)
    if not type(adapter).configured():
        messages.warning(request, type(adapter).unconfigured_note)
        return redirect("scheduling:availability")
    state = secrets.token_urlsafe(16)
    request.session[OAUTH_STATE_KEY] = {"state": state, "provider": provider}
    try:
        url = adapter.authorize_url(_callback_uri(request, provider), state)
    except Exception:
        messages.error(request, "Could not start the calendar connection. Try again later.")
        return redirect("scheduling:availability")
    return HttpResponseRedirect(url)


@login_required
@require_feature("scheduling")
def oauth_callback(request, provider):
    """Exchange the OAuth code and store the tokens on a CalendarConnection."""
    _company(request)
    adapter = _adapter_or_404(provider)
    stored = request.session.pop(OAUTH_STATE_KEY, None) or {}
    state = request.GET.get("state", "")
    code = request.GET.get("code", "")
    if request.GET.get("error"):
        messages.error(request, "Calendar connection was declined.")
        return redirect("scheduling:availability")
    if not code or stored.get("provider") != provider or stored.get("state") != state:
        messages.error(request, "Calendar connection could not be verified. Please retry.")
        return redirect("scheduling:availability")
    try:
        tokens = adapter.exchange_code(code, _callback_uri(request, provider), state)
    except Exception:
        messages.error(request, "The calendar provider rejected the connection.")
        return redirect("scheduling:availability")
    CalendarConnection.objects.update_or_create(
        user=request.user,
        provider=provider,
        defaults={
            "tokens": tokens or {},
            "enabled": True,
            "account_email": request.user.email,
            "last_synced": dj_timezone.now(),
        },
    )
    messages.success(request, f"{type(adapter).label} connected.")
    return redirect("scheduling:availability")


@login_required
@require_feature("scheduling")
@require_POST
def calendar_disconnect(request, pk):
    connection = get_object_or_404(CalendarConnection, pk=pk, user=request.user)
    connection.delete()
    messages.info(request, "Calendar disconnected.")
    return redirect("scheduling:availability")


# ------------------------------------------------------------ candidate


def _interview_by_token(token):
    """Token-authenticated lookup. A wrong token is indistinguishable from 404."""
    interview = (
        Interview.objects.filter(booking_token=token)
        .select_related("application__job__company", "application__candidate__user", "stage")
        .prefetch_related("interviewers")
        .first()
    )
    if interview is None:
        raise Http404("Unknown booking link.")
    return interview


def _expired(request, interview):
    return render(
        request,
        "scheduling/booking_expired.html",
        {"interview": interview},
        status=410,
    )


def _candidate_tz(request, interview):
    return valid_timezone(
        request.GET.get("tz") or request.POST.get("timezone") or interview.timezone
    )


def book(request, token):
    """Candidate self-service booking page: next 14 days of free slots."""
    interview = _interview_by_token(token)
    if interview.is_token_expired:
        return _expired(request, interview)
    tz = _candidate_tz(request, interview)
    interviewers = list(interview.interviewers.all())
    slots = []
    if interview.status in Interview.OPEN_STATUSES and interviewers:
        slots = services.free_slots(
            interviewers,
            duration_min=interview.duration_minutes,
            tz=tz,
            company=interview.company,
            exclude_interview=interview,
            limit=200,
        )
    context = {
        "interview": interview,
        "tz": tz,
        "days": services.slots_by_day(slots, tz),
        "slot_count": len(slots),
        "local_start": interview.local_start(tz),
        "local_end": interview.local_end(tz),
        "can_book": interview.status in Interview.OPEN_STATUSES and not interview.is_past,
        "cancel_form": CancelBookingForm(),
        "timezone_hint": tz,
    }
    if request.headers.get("HX-Request"):
        return render(request, "scheduling/partials/slot_picker.html", context)
    return render(request, "scheduling/book.html", context)


@require_POST
def book_confirm(request, token):
    """Confirm (or reschedule to) the chosen slot."""
    interview = _interview_by_token(token)
    if interview.is_token_expired:
        return _expired(request, interview)
    if interview.status not in Interview.OPEN_STATUSES or interview.is_past:
        messages.error(request, "This interview can no longer be changed.")
        return redirect("scheduling:book", token=token)
    form = BookingForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please pick one of the offered times.")
        return redirect("scheduling:book", token=token)
    start = form.cleaned_data["slot"]
    tz = form.cleaned_data["timezone"] or interview.timezone
    interview.timezone = tz
    interview.save(update_fields=["timezone", "updated_at"])
    was_scheduled = interview.scheduled_start is not None
    try:
        if was_scheduled:
            services.reschedule(interview, start)
        else:
            services.confirm(interview, start)
    except services.SlotUnavailable:
        messages.error(request, "Sorry, that time was just taken. Please pick another.")
        return redirect("scheduling:book", token=token)
    return redirect("scheduling:booked", token=token)


@require_POST
def book_cancel(request, token):
    """Candidate-side cancellation."""
    interview = _interview_by_token(token)
    if interview.is_token_expired:
        return _expired(request, interview)
    form = CancelBookingForm(request.POST)
    reason = form.cleaned_data.get("reason", "") if form.is_valid() else ""
    if interview.status in Interview.OPEN_STATUSES:
        services.cancel(interview, reason=reason)
    return redirect("scheduling:booked", token=token)


def booked(request, token):
    """Confirmation page shown after a booking, reschedule, or cancellation."""
    interview = _interview_by_token(token)
    tz = _candidate_tz(request, interview)
    return render(
        request,
        "scheduling/booked.html",
        {
            "interview": interview,
            "tz": tz,
            "local_start": interview.local_start(tz),
            "local_end": interview.local_end(tz),
        },
    )


def book_ics(request, token):
    """Candidate .ics download for a confirmed interview."""
    interview = _interview_by_token(token)
    if interview.is_token_expired:
        return _expired(request, interview)
    payload = interview_ics(interview)
    if not payload:
        raise Http404("This interview has no confirmed time yet.")
    response = HttpResponse(payload, content_type=MIMETYPE)
    response["Content-Disposition"] = f'attachment; filename="{FILENAME}"'
    return response
