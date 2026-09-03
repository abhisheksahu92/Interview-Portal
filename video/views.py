"""Views for the video app.

Recruiter screens are gated by ``billing.entitlements.require_feature("video")``
plus a company role; the candidate recorder is reached only through an invite
token (no login needed) and is bounded by the invite's deadline.
"""

import logging
import re

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from billing.entitlements import require_feature
from core.models import Membership
from core.permissions import for_company, role_required
from jobs.models import Application, Job, StageReview
from video import services, validators
from video.forms import QuickReviewForm, VideoQuestionForm, VideoScreenForm
from video.models import (
    ALLOWED_MIME_TYPES,
    MAX_RESPONSE_BYTES,
    VideoInvite,
    VideoQuestion,
    VideoResponse,
    VideoScreen,
    normalise_mime,
)

logger = logging.getLogger(__name__)

STAFF_ROLES = (Membership.OWNER, Membership.RECRUITER, Membership.INTERVIEWER)
MANAGE_ROLES = (Membership.OWNER, Membership.RECRUITER)
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
STREAM_CHUNK = 8192


# --------------------------------------------------------------------------
# Recruiter: overview
# --------------------------------------------------------------------------
def _company_screens(request):
    return VideoScreen.objects.filter(job__company=request.company).select_related(
        "job", "stage"
    )


def _company_invites(request):
    return VideoInvite.objects.filter(
        application__job__company=request.company
    ).select_related("application__job", "application__candidate__user", "screen")


@role_required(*STAFF_ROLES)
@require_feature("video")
def index(request):
    """Video screening home: screens, recent invites and library size."""
    invites = _company_invites(request)[:10]
    context = {
        "screens": _company_screens(request),
        "invites": invites,
        "question_count": for_company(
            VideoQuestion.objects.all(), request.company
        ).count(),
        "jobs": Job.objects.filter(company=request.company).order_by("title"),
        "can_manage": request.user.role_in(request.company) in MANAGE_ROLES,
    }
    return render(request, "video/index.html", context)


# --------------------------------------------------------------------------
# Recruiter: question library CRUD
# --------------------------------------------------------------------------
@role_required(*STAFF_ROLES)
@require_feature("video")
def question_list(request):
    questions = for_company(VideoQuestion.objects.all(), request.company)
    return render(
        request,
        "video/question_list.html",
        {
            "questions": questions,
            "can_manage": request.user.role_in(request.company) in MANAGE_ROLES,
        },
    )


@role_required(*MANAGE_ROLES)
@require_feature("video")
def question_create(request):
    form = VideoQuestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        question = form.save(commit=False)
        question.company = request.company
        question.save()
        messages.success(request, "Question added to the library.")
        return redirect("video:question_list")
    return render(
        request, "video/question_form.html", {"form": form, "is_new": True}
    )


@role_required(*MANAGE_ROLES)
@require_feature("video")
def question_edit(request, pk):
    question = get_object_or_404(
        for_company(VideoQuestion.objects.all(), request.company), pk=pk
    )
    form = VideoQuestionForm(request.POST or None, instance=question)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Question updated.")
        return redirect("video:question_list")
    return render(
        request,
        "video/question_form.html",
        {"form": form, "question": question, "is_new": False},
    )


@role_required(*MANAGE_ROLES)
@require_feature("video")
@require_POST
def question_delete(request, pk):
    question = get_object_or_404(
        for_company(VideoQuestion.objects.all(), request.company), pk=pk
    )
    question.delete()
    messages.success(request, "Question removed.")
    return redirect("video:question_list")


# --------------------------------------------------------------------------
# Recruiter: per-job screen builder
# --------------------------------------------------------------------------
@role_required(*STAFF_ROLES)
@require_feature("video")
def job_screens(request, job_id):
    job = get_object_or_404(Job.objects.filter(company=request.company), pk=job_id)
    return render(
        request,
        "video/job_screens.html",
        {
            "job": job,
            "screens": job.video_screens.select_related("stage"),
            "can_manage": request.user.role_in(request.company) in MANAGE_ROLES,
        },
    )


@role_required(*MANAGE_ROLES)
@require_feature("video")
def screen_create(request, job_id):
    job = get_object_or_404(Job.objects.filter(company=request.company), pk=job_id)
    form = VideoScreenForm(request.POST or None, job=job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Video screen saved.")
        return redirect("video:job_screens", job_id=job.pk)
    return render(
        request, "video/screen_form.html", {"form": form, "job": job, "is_new": True}
    )


@role_required(*MANAGE_ROLES)
@require_feature("video")
def screen_edit(request, pk):
    screen = get_object_or_404(_company_screens(request), pk=pk)
    form = VideoScreenForm(request.POST or None, instance=screen, job=screen.job)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Video screen updated.")
        return redirect("video:job_screens", job_id=screen.job_id)
    return render(
        request,
        "video/screen_form.html",
        {"form": form, "job": screen.job, "screen": screen, "is_new": False},
    )


@role_required(*MANAGE_ROLES)
@require_feature("video")
@require_POST
def screen_delete(request, pk):
    screen = get_object_or_404(_company_screens(request), pk=pk)
    job_id = screen.job_id
    screen.delete()
    messages.success(request, "Video screen deleted.")
    return redirect("video:job_screens", job_id=job_id)


@role_required(*MANAGE_ROLES)
@require_feature("video")
@require_POST
def invite_create(request, screen_id, application_id):
    """Manually invite one application to a screen."""
    screen = get_object_or_404(_company_screens(request), pk=screen_id)
    application = get_object_or_404(
        Application.objects.filter(job__company=request.company), pk=application_id
    )
    services.create_invite(application, screen)
    messages.success(request, "Video invite sent.")
    return redirect("video:invite_list")


# --------------------------------------------------------------------------
# Recruiter: invites + review
# --------------------------------------------------------------------------
@role_required(*STAFF_ROLES)
@require_feature("video")
def invite_list(request):
    invites = _company_invites(request)
    status = request.GET.get("status") or ""
    if status:
        invites = invites.filter(status=status)
    return render(
        request,
        "video/invite_list.html",
        {
            "invites": invites,
            "status": status,
            "status_choices": VideoInvite.STATUS_CHOICES,
        },
    )


@role_required(*STAFF_ROLES)
@require_feature("video")
def invite_review(request, pk):
    """Playback + transcript + AI summary, with a quick StageReview form."""
    invite = get_object_or_404(_company_invites(request), pk=pk)
    application = invite.application
    stage = application.current_stage or invite.screen.stage
    form = QuickReviewForm(request.POST or None)
    if request.method == "POST":
        if stage is None:
            messages.error(request, "This application has no stage to review.")
        elif form.is_valid():
            services.write_review(
                application,
                stage,
                request.user,
                form.cleaned_data["decision"],
                rating=form.cleaned_data.get("rating") or None,
                feedback=form.cleaned_data.get("feedback", ""),
            )
            messages.success(request, "Review recorded.")
            return redirect("video:invite_review", pk=invite.pk)
    responses = invite.responses.select_related("question")
    return render(
        request,
        "video/invite_review.html",
        {
            "invite": invite,
            "application": application,
            "stage": stage,
            "responses": responses,
            "form": form,
            "decisions": StageReview.DECISION_CHOICES,
        },
    )


# --------------------------------------------------------------------------
# Streaming (permission-checked, Range-aware)
# --------------------------------------------------------------------------
def _may_stream(request, response):
    """A company member (feature-gated) or the owning candidate may watch."""
    user = request.user
    if not user.is_authenticated:
        return False
    company = response.invite.company
    if user.role_in(company) in STAFF_ROLES:
        from billing.entitlements import has_feature

        return has_feature(company, "video")
    candidate = getattr(user, "candidate_profile", None)
    return candidate is not None and candidate.pk == response.invite.application.candidate_id


def response_stream(request, pk):
    """Serve a recording with HTTP Range support so <video> can seek."""
    response_row = get_object_or_404(
        VideoResponse.objects.select_related(
            "invite__application__job__company", "invite__application__candidate"
        ),
        pk=pk,
    )
    if not _may_stream(request, response_row):
        raise PermissionDenied("You may not watch this recording.")
    if not response_row.file:
        raise Http404("No recording stored.")

    try:
        size = response_row.file.size
    except (OSError, ValueError) as exc:
        raise Http404("Recording file is missing.") from exc
    content_type = response_row.mime or "video/webm"

    range_header = request.META.get("HTTP_RANGE", "")
    match = RANGE_RE.match(range_header or "")
    if not match:
        reply = FileResponse(
            response_row.file.open("rb"), content_type=content_type
        )
        reply["Content-Length"] = str(size)
        reply["Accept-Ranges"] = "bytes"
        return reply

    start_raw, end_raw = match.groups()
    if start_raw:
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
    else:  # suffix range: bytes=-500
        length = int(end_raw or 0)
        start = max(0, size - length)
        end = size - 1
    end = min(end, size - 1)
    if start >= size or start > end:
        reply = HttpResponse(status=416)
        reply["Content-Range"] = f"bytes */{size}"
        return reply

    handle = response_row.file.open("rb")
    handle.seek(start)
    remaining = end - start + 1

    def chunks():
        left = remaining
        try:
            while left > 0:
                data = handle.read(min(STREAM_CHUNK, left))
                if not data:
                    break
                left -= len(data)
                yield data
        finally:
            handle.close()

    reply = StreamingHttpResponse(chunks(), status=206, content_type=content_type)
    reply["Content-Range"] = f"bytes {start}-{end}/{size}"
    reply["Content-Length"] = str(remaining)
    reply["Accept-Ranges"] = "bytes"
    return reply


# --------------------------------------------------------------------------
# Candidate recorder (token based, no login)
# --------------------------------------------------------------------------
def _open_invite(token):
    """Fetch an invite by token, expiring it server-side when past deadline."""
    invite = get_object_or_404(
        VideoInvite.objects.select_related(
            "screen", "application__job", "application__candidate__user"
        ),
        token=token,
    )
    if invite.is_expired:
        invite.mark_expired()
    return invite


def take(request, token):
    """Intro page: camera/mic check, then the question runner."""
    invite = _open_invite(token)
    if invite.status == VideoInvite.SUBMITTED:
        return redirect("video:take_done", token=token)
    if not invite.is_open:
        return render(
            request, "video/take_closed.html", {"invite": invite}, status=410
        )
    questions = list(invite.screen.ordered_questions())
    answered = invite.answered_question_ids()
    return render(
        request,
        "video/take.html",
        {
            "invite": invite,
            "questions": questions,
            "answered_ids": sorted(answered),
            "next_question": invite.next_question(),
            "max_bytes": MAX_RESPONSE_BYTES,
            "upload_url": reverse("video:take_upload", args=[token]),
            "submit_url": reverse("video:take_submit", args=[token]),
        },
    )


@csrf_protect
def take_upload(request, token):
    """Accept one recording (multipart) for one question. Returns JSON."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    invite = _open_invite(token)
    if not invite.is_open:
        return JsonResponse(
            {"ok": False, "error": "This video screen is closed."}, status=410
        )

    try:
        question_id = int(request.POST.get("question") or 0)
    except (TypeError, ValueError):
        question_id = 0
    question = invite.screen.questions.filter(pk=question_id).first()
    if question is None:
        return JsonResponse(
            {"ok": False, "error": "Unknown question."}, status=400
        )
    if invite.responses.filter(question=question).exists():
        return JsonResponse(
            {"ok": False, "error": "This question is already answered."}, status=409
        )

    upload = request.FILES.get("file")
    if upload is None:
        return JsonResponse({"ok": False, "error": "No recording received."}, status=400)
    if upload.size > MAX_RESPONSE_BYTES:
        return JsonResponse(
            {"ok": False, "error": "Recording is larger than the 200 MB limit."},
            status=413,
        )
    mime = normalise_mime(getattr(upload, "content_type", "") or "")
    extension = validators.extension_of(upload.name)
    if mime not in ALLOWED_MIME_TYPES and extension not in ("webm", "mp4"):
        return JsonResponse(
            {"ok": False, "error": "Only .webm and .mp4 recordings are accepted."},
            status=415,
        )
    if mime not in ALLOWED_MIME_TYPES:
        mime = "video/mp4" if extension == "mp4" else "video/webm"

    # The declared type is candidate-controlled; check the container's bytes.
    try:
        sniffed = validators.check_container(upload, mime, extension)
    except validators.UnsupportedContainer as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=415)
    if sniffed:
        mime = f"video/{sniffed}"
        extension = sniffed

    if not (upload.name or "").lower().endswith((".webm", ".mp4")):
        upload.name = f"answer.{'mp4' if mime == 'video/mp4' else 'webm'}"

    # Video minutes are billed, so never trust the client's duration: read the
    # real one when that is cheap, and cap it at what the question allowed.
    duration = validators.metered_duration(
        upload, request.POST.get("duration"), question
    )

    if not services.consume_minutes(invite.company, duration):
        return JsonResponse(
            {"ok": False, "error": "This workspace is out of video minutes."},
            status=402,
        )

    try:
        response_row = services.record_upload(
            invite, question, upload, duration_seconds=duration, mime=mime
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)

    remaining = invite.next_question()
    return JsonResponse(
        {
            "ok": True,
            "response_id": response_row.pk,
            "answered": invite.responses.count(),
            "total": invite.screen.questions.count(),
            "next_question_id": remaining.pk if remaining else None,
        }
    )


@require_POST
def take_submit(request, token):
    """Finish the screen: mark SUBMITTED once every question is answered."""
    invite = _open_invite(token)
    if invite.status == VideoInvite.SUBMITTED:
        return redirect("video:take_done", token=token)
    if not invite.is_open:
        return render(request, "video/take_closed.html", {"invite": invite}, status=410)
    if invite.next_question() is not None:
        messages.error(request, "Please answer every question before submitting.")
        return redirect("video:take", token=token)
    invite.mark_submitted()
    return redirect("video:take_done", token=token)


def take_done(request, token):
    """Thank-you page after submitting."""
    invite = get_object_or_404(
        VideoInvite.objects.select_related("screen", "application__job"), token=token
    )
    return render(request, "video/take_done.html", {"invite": invite})
