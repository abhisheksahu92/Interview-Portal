"""Post-upload processing for video responses: transcript then AI review."""

import logging

from django.utils import timezone

from video.models import VideoResponse

logger = logging.getLogger(__name__)

NO_TRANSCRIPT_SUMMARY = "Transcript unavailable"


def process_response(response):
    """Fill transcript + AI summary/score for one response. Never raises.

    Transcription runs through the env-gated ``video.gateway``; when no key is
    configured the transcript stays blank and the summary says so. With a
    transcript we ask ``video.ai`` for a summary and 0-100 score.
    """
    from video import ai, gateway

    try:
        transcript = gateway.transcribe(response) if gateway.configured() else ""
    except Exception:  # pragma: no cover - gateway already swallows
        logger.exception("Transcription raised for response %s.", response.pk)
        transcript = ""

    response.transcript = transcript or ""
    if not response.transcript:
        response.ai_summary = NO_TRANSCRIPT_SUMMARY
        response.ai_score = None
        response.status = VideoResponse.PROCESSED
    else:
        review = None
        try:
            review = ai.review_answer(response.question.text, response.transcript)
        except Exception:
            logger.exception("AI review raised for response %s.", response.pk)
        if review is None:
            response.ai_summary = ""
            response.ai_score = None
            response.status = VideoResponse.PROCESSED
        else:
            response.ai_summary = review.get("summary") or ""
            response.ai_score = review.get("score")
            response.status = VideoResponse.PROCESSED

    response.processed_at = timezone.now()
    response.save(
        update_fields=["transcript", "ai_summary", "ai_score", "status", "processed_at"]
    )
    return response


def pending_responses():
    """Responses that have not been through :func:`process_response` yet."""
    return VideoResponse.objects.filter(status=VideoResponse.UPLOADED)


def process_pending(limit=None):
    """Process every UPLOADED response; returns the number handled."""
    qs = pending_responses().select_related("question", "invite")
    if limit:
        qs = qs[:limit]
    count = 0
    for response in qs:
        try:
            process_response(response)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Could not process response %s.", response.pk)
            VideoResponse.objects.filter(pk=response.pk).update(
                status=VideoResponse.FAILED
            )
            continue
        count += 1
    return count
