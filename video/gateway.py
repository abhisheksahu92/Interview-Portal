"""External-service adapter for video transcription.

Environment variables:
  ``VIDEO_TRANSCRIBE_API_KEY``  -- key for the speech-to-text provider
  ``VIDEO_TRANSCRIBE_URL``      -- provider endpoint (optional; has a default)

``configured()`` returns False until both the provider key is set, so callers
degrade gracefully (blank transcript) and tests never touch the network.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://api.example-speech.test/v1/transcribe"


def _key():
    return getattr(settings, "VIDEO_TRANSCRIBE_API_KEY", "") or ""


def _url():
    return getattr(settings, "VIDEO_TRANSCRIBE_URL", "") or DEFAULT_URL


def configured() -> bool:
    """True when this gateway has everything it needs to call out."""
    return bool(_key())


def transcribe(response) -> str:
    """Transcribe a :class:`video.models.VideoResponse`; ``""`` when unavailable.

    Never raises: any provider/network failure is logged and downgraded to an
    empty transcript so processing can still mark the response reviewed.
    """
    if not configured():
        logger.info("Video transcription is not configured; leaving transcript blank.")
        return ""
    try:
        import requests

        with response.file.open("rb") as handle:
            reply = requests.post(
                _url(),
                headers={"Authorization": f"Bearer {_key()}"},
                files={"file": (response.file.name, handle, response.mime or "video/webm")},
                timeout=120,
            )
        reply.raise_for_status()
        payload = reply.json()
    except Exception:
        logger.exception("Video transcription failed; leaving transcript blank.")
        return ""
    text = payload.get("text") if isinstance(payload, dict) else None
    return str(text or "").strip()
