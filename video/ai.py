"""Thin Anthropic wrapper for reviewing video-screen answers.

Mirrors ``assessments.ai``: every public function degrades gracefully -- with no
``ANTHROPIC_API_KEY`` (or on any SDK/API/parse failure) it logs and returns
``None`` instead of raising into a request.
"""

import json
import logging
import re

from django.conf import settings

from core import llm

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5"
MAX_TOKENS = 1024

SYSTEM_PROMPT = (
    "You are an expert technical hiring assistant reviewing a candidate's "
    "recorded video answer. You reply with JSON only - no prose, no markdown fences."
)

REVIEW_PROMPT = """\
Review this transcript of a candidate's recorded video answer.

Question:
{question}

Transcript:
{transcript}

Return JSON: {{"score": <integer 0-100>, "summary": "<two or three sentences>"}}
Judge relevance, depth, structure and communication. Be concrete and skeptical.
"""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "summary": {"type": "string"},
    },
    "required": ["score", "summary"],
    "additionalProperties": False,
}


def get_client():
    """Return an Anthropic client, or ``None`` when unusable/unconfigured."""
    key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    if not key:
        logger.warning("ANTHROPIC_API_KEY is not set; video AI review is disabled.")
        return None
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is pinned
        logger.warning("anthropic SDK is not installed; video AI review is disabled.")
        return None
    try:
        return anthropic.Anthropic(api_key=key)
    except Exception:
        logger.exception("Could not build the Anthropic client.")
        return None


def _extract_json(text):
    """Best-effort parse of a JSON object out of a model response."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except ValueError:
            pass
    logger.warning("Could not parse JSON from the model response.")
    return None


def _ask(prompt, schema=None):
    """Send one prompt and return the parsed JSON object, or ``None``."""
    text = llm.complete(
        prompt,
        system=SYSTEM_PROMPT,
        max_tokens=MAX_TOKENS,
        schema=schema,
        model=MODEL if llm.active_provider() == "anthropic" else "",
    )
    if text is None:
        return None
    return _extract_json(text)


def _clamp_score(value):
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def review_answer(question_text, transcript):
    """Return ``{"score": int|None, "summary": str}`` for a transcript, or ``None``."""
    if not (transcript or "").strip():
        return None
    data = _ask(
        REVIEW_PROMPT.format(question=question_text or "", transcript=transcript),
        schema=REVIEW_SCHEMA,
    )
    if not isinstance(data, dict):
        return None
    return {
        "score": _clamp_score(data.get("score")),
        "summary": str(data.get("summary") or "").strip(),
    }
