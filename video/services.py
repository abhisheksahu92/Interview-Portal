"""Domain services for the video app: invites, notifications and usage."""

import logging
import math

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from video.models import VideoInvite, VideoResponse

logger = logging.getLogger(__name__)

USAGE_KIND = "VIDEO_MINUTE"


def screen_for_stage(stage):
    """The active screen configured for ``stage`` (or its job), or ``None``."""
    if stage is None:
        return None
    from video.models import VideoScreen

    screen = VideoScreen.objects.filter(stage=stage, is_active=True).first()
    if screen is not None:
        return screen
    return VideoScreen.objects.filter(
        job=stage.job, stage__isnull=True, is_active=True
    ).first()


def invite_url(invite, request=None):
    """Absolute (when a request is given) recorder URL for an invite."""
    path = reverse("video:take", args=[invite.token])
    if request is not None:
        return request.build_absolute_uri(path)
    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base else path


def create_invite(application, screen, notify=True):
    """Create (or return) the invite for ``application`` on ``screen``."""
    invite, created = VideoInvite.objects.get_or_create(
        application=application, screen=screen
    )
    if created and notify:
        notify_invite(invite)
    return invite


def notify_invite(invite):
    """Tell the candidate about a new invite. Never raises."""
    user = getattr(invite.application.candidate, "user", None)
    email = getattr(user, "email", "") or ""
    context = {
        "job_title": invite.application.job.title,
        "screen_title": invite.screen.title,
        "url": invite_url(invite),
        "expires_at": invite.expires_at,
        "question_count": invite.screen.questions.count(),
    }
    try:
        from notifications import send

        send("video_invite", user or email, context, invite.company)
        return True
    except Exception:
        logger.info("notifications.send unavailable; falling back to email.", exc_info=True)

    if not email:
        return False
    try:
        send_mail(
            subject=f"Record your video answers for {context['job_title']}",
            message=(
                f"Please complete the '{context['screen_title']}' video screen for "
                f"{context['job_title']}.\n\n{context['url']}\n\n"
                f"The link expires on {invite.expires_at:%d %b %Y}."
            ),
            from_email=None,
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception:  # pragma: no cover - fail_silently already set
        logger.exception("Could not email the video invite.")
        return False
    return True


def consume_minutes(company, duration_seconds):
    """Consume VIDEO_MINUTE usage for a recording. Missing billing = unlimited.

    Returns True when metering succeeded or was unavailable, False when the
    company is over quota (the caller should refuse the upload).
    """
    units = max(1, math.ceil((duration_seconds or 0) / 60))
    try:
        from billing.usage import consume
    except Exception:
        logger.debug("billing.usage unavailable; video minutes are unmetered.")
        return True
    try:
        consume(company, USAGE_KIND, units)
    except Exception as exc:
        if type(exc).__name__ == "QuotaExceeded":
            logger.warning("Video minute quota exceeded for %s.", company)
            return False
        logger.exception("Video usage metering failed; allowing the upload.")
    return True


def record_upload(invite, question, upload, duration_seconds=0, mime=""):
    """Persist one response and mark the invite in progress."""
    response = VideoResponse.objects.create(
        invite=invite,
        question=question,
        file=upload,
        duration_seconds=duration_seconds or 0,
        mime=mime or "",
        status=VideoResponse.UPLOADED,
    )
    invite.mark_started()
    return response


def expire_stale_invites():
    """Flip open invites past their deadline to EXPIRED; returns the count."""
    stale = VideoInvite.objects.filter(
        status__in=[VideoInvite.PENDING, VideoInvite.IN_PROGRESS],
        expires_at__lte=timezone.now(),
    )
    return stale.update(status=VideoInvite.EXPIRED)


def write_review(application, stage, reviewer, decision, rating=None, feedback=""):
    """Write a jobs.StageReview through jobs.services (late import)."""
    from jobs.services import record_review

    return record_review(
        application, stage, reviewer, decision, rating=rating, feedback=feedback
    )
