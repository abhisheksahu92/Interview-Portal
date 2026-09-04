"""Clients app views: recruiter management screens plus the tokenised client portal.

Recruiter views are gated on the ``client_portal`` entitlement
(:func:`billing.entitlements.require_feature`). Portal views are deliberately
un-gated by login and authenticated purely by the ``ClientAccess`` token in the URL.
"""

import mimetypes
import os
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from billing.entitlements import require_feature
from clients import services
from clients.forms import (
    ClientAccessForm,
    ClientFeedbackForm,
    ClientForm,
    JobClientForm,
    SubmitToClientForm,
)
from clients.models import Client, ClientAccess, Submission
from core.models import Membership
from core.permissions import role_required
from core.tokens import resolve_token, token_invalid_response
from jobs.models import Application, Job

RECRUITER_ROLES = (Membership.OWNER, Membership.RECRUITER)


def _recruiter_view(view_func):
    """login + tenant role + feature gate, in that order."""
    return login_required(role_required(*RECRUITER_ROLES)(require_feature("client_portal")(view_func)))


def _get_client(request, pk):
    return get_object_or_404(Client.objects.for_company(request.company), pk=pk)


# --------------------------------------------------------------------------- #
# Recruiter screens
# --------------------------------------------------------------------------- #


@_recruiter_view
def index(request):
    """List every client of the active company."""
    clients = Client.objects.for_company(request.company).prefetch_related(
        "jobs", "submissions", "accesses"
    )
    return render(request, "clients/client_list.html", {"clients": clients})


@_recruiter_view
def create(request):
    form = ClientForm(request.POST or None, request.FILES or None, company=request.company)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        messages.success(request, f"Client “{client.name}” created.")
        return redirect("clients:detail", pk=client.pk)
    return render(
        request, "clients/client_form.html", {"form": form, "mode": "create"}
    )


@_recruiter_view
def edit(request, pk):
    client = _get_client(request, pk)
    form = ClientForm(
        request.POST or None, request.FILES or None, instance=client, company=request.company
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Client updated.")
        return redirect("clients:detail", pk=client.pk)
    return render(
        request,
        "clients/client_form.html",
        {"form": form, "mode": "edit", "client": client},
    )


@_recruiter_view
def detail(request, pk):
    client = _get_client(request, pk)
    context = services.client_dashboard_context(client)
    context["access_form"] = ClientAccessForm()
    context["unassigned_jobs"] = Job.objects.filter(
        company=request.company, client__isnull=True
    ).order_by("title")
    return render(request, "clients/client_detail.html", context)


@_recruiter_view
def submission_detail(request, pk):
    """Recruiter-facing submission status timeline."""
    submission = get_object_or_404(
        Submission.objects.select_related("client", "application__job", "application__candidate__user"),
        pk=pk,
        client__company=request.company,
    )
    return render(
        request,
        "clients/submission_detail.html",
        {"submission": submission, "timeline": submission.timeline()},
    )


@_recruiter_view
def submit_application(request, application_id):
    """Submit one application to a client (defaults to the job's own client)."""
    application = get_object_or_404(
        Application.objects.select_related("job", "candidate__user"),
        pk=application_id,
        job__company=request.company,
    )
    form = SubmitToClientForm(
        request.POST or None, company=request.company, application=application
    )
    if request.method == "POST" and form.is_valid():
        submission, _created = services.submit_application(
            application,
            form.cleaned_data["client"],
            submitted_by=request.user,
            note=form.cleaned_data["note"],
            notify=form.cleaned_data["notify_client"],
        )
        messages.success(request, f"Submitted to {submission.client.name}.")
        return redirect("clients:submission_detail", pk=submission.pk)
    return render(
        request,
        "clients/submit_to_client.html",
        {"form": form, "application": application},
    )


@_recruiter_view
@require_POST
def access_create(request, pk):
    client = _get_client(request, pk)
    form = ClientAccessForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid email address and expiry.")
        return redirect("clients:detail", pk=client.pk)
    access = services.issue_access(
        client, form.cleaned_data["email"], valid_days=form.cleaned_data["valid_days"]
    )
    services.send_access_link(access, request)
    messages.success(request, f"Portal link sent to {access.email}.")
    return redirect("clients:detail", pk=client.pk)


@_recruiter_view
@require_POST
def access_revoke(request, pk, access_id):
    client = _get_client(request, pk)
    access = get_object_or_404(ClientAccess, pk=access_id, client=client)
    access.revoke()
    messages.success(request, f"Access for {access.email} revoked.")
    return redirect("clients:detail", pk=client.pk)


@_recruiter_view
@require_POST
def access_resend(request, pk, access_id):
    """Rotate the token (invalidating the old link) and email the new one."""
    client = _get_client(request, pk)
    access = get_object_or_404(ClientAccess, pk=access_id, client=client)
    access.rotate()
    services.send_access_link(access, request)
    messages.success(request, f"A fresh link was emailed to {access.email}.")
    return redirect("clients:detail", pk=client.pk)


@_recruiter_view
def job_client(request, job_id):
    """Set/clear a job's end client. Linked from the client detail page and
    usable by web/'s job screens (see clients.forms.JobClientForm)."""
    job = get_object_or_404(Job, pk=job_id, company=request.company)
    form = JobClientForm(request.POST or None, company=request.company, job=job)
    if request.method == "POST" and form.is_valid():
        form.apply(job)
        messages.success(request, f"Client for “{job.title}” updated.")
        target = form.cleaned_data.get("client")
        if target is not None:
            return redirect("clients:detail", pk=target.pk)
        return redirect("clients:index")
    return render(request, "clients/job_client_form.html", {"form": form, "job": job})


# --------------------------------------------------------------------------- #
# Client portal (no login — token in the URL)
# --------------------------------------------------------------------------- #


def portal_guard(view_func):
    """Resolve the URL token to a live ClientAccess or render the 404 page.

    The wrapped view is called as ``view(request, access, *args)`` — expired and
    revoked links never reach it. Resolution/rendering is shared with the rest
    of the app via :mod:`core.tokens`.
    """

    @wraps(view_func)
    def _wrapped(request, token, *args, **kwargs):
        resolution = resolve_token(
            ClientAccess, token, select_related=("client__company",)
        )
        if not resolution.ok:
            access = resolution.obj
            client = getattr(access, "client", None)
            # Portal links answer 404 for every bad state (expired, revoked and
            # unknown alike) so the page never confirms that a token exists.
            return token_invalid_response(
                request,
                resolution,
                status=404,
                context={
                    "base_template": "clients/portal/base.html",
                    "access": access,
                    "client": client,
                    "brand_name": getattr(client, "name", ""),
                    "provider_name": getattr(
                        getattr(client, "company", None), "name", ""
                    ),
                    "page_title": "Link no longer valid",
                    "contact_hint": (
                        "Please contact your recruiting partner to have a fresh "
                        "link sent to you."
                    ),
                },
            )
        return view_func(request, resolution.obj, *args, **kwargs)

    return _wrapped


def _portal_context(access):
    client = access.client
    return {
        "access": access,
        "client": client,
        # White-label friendly: the portal never reads request.company, only the
        # client's own branding plus the providing firm's name.
        "brand_name": client.name,
        "provider_name": client.company.name,
        "groups": services.grouped_submissions(client),
    }


@portal_guard
def portal(request, access):
    access.touch()
    context = _portal_context(access)
    context["feedback_form"] = ClientFeedbackForm()
    return render(request, "clients/portal/portal.html", context)


@portal_guard
def portal_resume(request, access, submission_id):
    """Stream a candidate's resume; never exposes the /media path."""
    submission = get_object_or_404(
        Submission.objects.select_related("application__candidate"),
        pk=submission_id,
        client=access.client,
    )
    resume = submission.application.candidate.resume
    if not resume:
        raise Http404("No resume on file for this candidate.")
    content_type = mimetypes.guess_type(resume.name)[0] or "application/octet-stream"
    try:
        handle = resume.open("rb")
    except (FileNotFoundError, OSError) as exc:  # storage lost the file
        raise Http404("Resume file is unavailable.") from exc
    extension = os.path.splitext(resume.name)[1] or ".pdf"
    filename = f"resume-{submission.pk}{extension}"
    return FileResponse(
        handle, as_attachment=True, filename=filename, content_type=content_type
    )


@require_POST
@portal_guard
def portal_feedback(request, access, submission_id):
    """Record a client decision, lightly rate-limited per access token."""
    submission = get_object_or_404(Submission, pk=submission_id, client=access.client)

    cooldown_key = f"clients:feedback:{access.token}"
    if cache.get(cooldown_key):
        messages.error(request, "Please wait a moment before sending more feedback.")
        return redirect("clients:portal", token=access.token)
    cache.set(cooldown_key, 1, services.FEEDBACK_COOLDOWN_SECONDS)

    form = ClientFeedbackForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a decision before submitting.")
        return redirect("clients:portal", token=access.token)

    submission.record_client_decision(
        form.cleaned_data["decision"],
        feedback=form.cleaned_data["comment"],
        rating=form.cleaned_data["rating"] or None,
    )
    access.touch()
    services.notify_recruiter_of_feedback(submission, request)
    messages.success(request, "Thanks — your feedback has been sent to the recruiter.")
    return redirect("clients:portal", token=access.token)
