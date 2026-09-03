"""Claude-backed structured extraction for talent-pool resumes.

Mirrors the client/degradation pattern of ``assessments.ai``: with no
``ANTHROPIC_API_KEY`` (or on any SDK/API/parse failure) every function logs and
returns ``None`` so imports keep working on regex heuristics alone. Callers must
also check ``billing.entitlements.has_feature(company, "ai_extraction")``-style
gating themselves — see ``talent.services``.
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5"
MAX_TOKENS = 1024
MAX_RESUME_CHARS = 8_000

SYSTEM_PROMPT = (
    "You are a resume parser for a recruiting platform. "
    "You reply with JSON only - no prose, no markdown fences."
)

EXTRACT_PROFILE_PROMPT = """\
Extract structured details from this resume text.

Resume text:
{text}

Return JSON of exactly this shape:
{{"name": "<full name or empty string>",
  "email": "<email or empty string>",
  "phone": "<phone or empty string>",
  "headline": "<short current title, max 120 chars>",
  "current_company": "<most recent employer or empty string>",
  "location": "<city, country or empty string>",
  "experience_years": <number or null>,
  "skills": ["<skill>", ...]}}
Use an empty string / null / empty list for anything the resume does not state.
Give at most 20 skills, each a short technology or discipline name.
"""


def get_client():
    """Return an Anthropic client, or ``None`` when unusable/unconfigured."""
    key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    if not key:
        logger.warning("ANTHROPIC_API_KEY is not set; talent AI extraction is disabled.")
        return None
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is pinned
        logger.warning("anthropic SDK is not installed; talent AI extraction is disabled.")
        return None
    try:
        return anthropic.Anthropic(api_key=key)
    except Exception:
        logger.exception("Could not build the Anthropic client.")
        return None


def is_configured():
    """True when an API key is present (no network call)."""
    return bool(getattr(settings, "ANTHROPIC_API_KEY", "") or "")


def _extract_json(text):
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


def _ask(prompt):
    client = get_client()
    if client is None:
        return None
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
    except Exception:
        logger.exception("Anthropic request failed; degrading gracefully.")
        return None
    return _extract_json(text)


def _clean_str(value, limit):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()[:limit]


def extract_profile(resume_text):
    """Return a normalised profile dict from ``resume_text``, or ``None``.

    Keys: name, email, phone, headline, current_company, location,
    experience_years (float|None), skills (list[str]).
    """
    resume_text = (resume_text or "").strip()
    if not resume_text:
        return None
    data = _ask(EXTRACT_PROFILE_PROMPT.format(text=resume_text[:MAX_RESUME_CHARS]))
    if not isinstance(data, dict):
        return None

    from talent.parsing import split_skills

    years = data.get("experience_years")
    try:
        years = round(float(years), 1) if years is not None else None
    except (TypeError, ValueError):
        years = None
    if years is not None and not (0 <= years <= 60):
        years = None

    return {
        "name": _clean_str(data.get("name"), 150),
        "email": _clean_str(data.get("email"), 254).lower(),
        "phone": _clean_str(data.get("phone"), 30),
        "headline": _clean_str(data.get("headline"), 200),
        "current_company": _clean_str(data.get("current_company"), 150),
        "location": _clean_str(data.get("location"), 150),
        "experience_years": years,
        "skills": split_skills(data.get("skills"))[:20],
    }
