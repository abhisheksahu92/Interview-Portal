"""Thin Anthropic wrapper for assessment/screening AI features.

Every public function degrades gracefully: with no ``ANTHROPIC_API_KEY`` (or on
any SDK/API/parse failure) it logs a warning and returns ``None``/``[]`` instead
of raising into a request.
"""

import json
import logging
import re

from django.conf import settings
from django.utils import timezone

from core import llm

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5"
MAX_TOKENS = 4096

# --- Prompts (single place) ----------------------------------------------
SYSTEM_PROMPT = (
    "You are an expert technical hiring assistant for an IT staffing firm. "
    "You reply with JSON only - no prose, no markdown fences."
)

GENERATE_QUESTIONS_PROMPT = """\
Write {n} {kind} interview screening questions for this role.

Job title: {title}
Skill focus: {skill}
Job description:
{description}

Requirements:
{requirements}

Return JSON of the form:
{{"questions": [{{"text": "...", "options": ["a", "b", "c", "d"],
  "correct_option": 0, "difficulty": "EASY|MEDIUM|HARD"}}]}}
For MCQ questions give exactly 4 options and a 0-based "correct_option".
For TEXT questions use an empty "options" list and null "correct_option".
"""

GRADE_TEXT_PROMPT = """\
Grade a candidate's free-text answer from 0 to 100 on correctness, depth and clarity.

Question:
{question}

Candidate answer:
{answer}

Return JSON: {{"score": <integer 0-100>, "feedback": "<one or two sentences>"}}
"""

SUMMARIZE_FIT_PROMPT = """\
Assess how well this candidate fits the role. Be concrete and skeptical: reward
evidence found in the resume, and call out requirements you cannot verify.

# Role
Job title: {title}
Job description:
{description}

Job requirements:
{requirements}

Required skills: {job_skills}

# Candidate
Headline: {headline}
Years of experience (self-reported): {experience_years}
Self-reported skills: {candidate_skills}
Notice period (days): {notice_period_days}
Resume text (may be empty):
{resume_text}

# Output
Return JSON only, of exactly this shape:
{{"fit_score": <integer 0-100>,
  "summary": "<exactly 3 sentences: match, gaps, recommendation>",
  "strengths": ["<short phrase>", ...],
  "gaps": ["<short phrase>", ...],
  "flagged_skills": ["<required skill with no supporting evidence>", ...]}}
Use an empty list when a section has nothing to report. Score 0-100 where 100 is
a perfect match; if the resume text is empty, judge on the profile alone and say so.
"""


# --- Client ---------------------------------------------------------------
def get_client():
    """Return an Anthropic client, or ``None`` when unusable/unconfigured."""
    key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    if not key:
        logger.warning("ANTHROPIC_API_KEY is not set; AI features are disabled.")
        return None
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is pinned
        logger.warning("anthropic SDK is not installed; AI features are disabled.")
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
    """Send one prompt and return the parsed JSON object, or ``None``.

    When the installed SDK supports structured outputs and a ``schema`` is
    given, the response format is constrained server-side; otherwise we fall
    back to tolerant JSON extraction from the text response.
    """
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


# --- Public API -----------------------------------------------------------
def generate_questions(job, skill=None, n=5, kind="MCQ"):
    """Generate and save ``n`` questions for ``job``/``skill``. Returns a list."""
    from assessments.models import Question

    kind = kind if kind in {Question.MCQ, Question.TEXT} else Question.MCQ
    prompt = GENERATE_QUESTIONS_PROMPT.format(
        n=max(1, min(20, int(n or 5))),
        kind="multiple-choice" if kind == Question.MCQ else "free-text",
        title=getattr(job, "title", ""),
        skill=getattr(skill, "name", "general"),
        description=getattr(job, "description", "") or "",
        requirements=getattr(job, "requirements", "") or "",
    )
    data = _ask(prompt)
    if not data:
        return []

    items = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(items, list):
        logger.warning("Unexpected question payload from the model.")
        return []

    created = []
    valid_difficulties = {c[0] for c in Question.DIFFICULTY_CHOICES}
    for item in items:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        options = item.get("options") or []
        if not isinstance(options, list):
            options = []
        options = [str(o) for o in options]
        correct = item.get("correct_option")
        if kind == Question.MCQ:
            if len(options) < 2:
                continue
            correct = _clamp_score(correct)
            if correct is None or correct >= len(options):
                correct = 0
        else:
            options, correct = [], None
        difficulty = str(item.get("difficulty", "")).upper()
        created.append(
            Question.objects.create(
                company=job.company,
                skill=skill,
                kind=kind,
                text=str(item["text"]),
                options=options,
                correct_option=correct,
                difficulty=(difficulty if difficulty in valid_difficulties else Question.MEDIUM),
                source=Question.AI,
            )
        )
    return created


def grade_text_answer(question, answer):
    """Return an int 0-100 for a free-text answer, or ``None``."""
    if not answer:
        return None
    data = _ask(
        GRADE_TEXT_PROMPT.format(question=getattr(question, "text", str(question)), answer=answer)
    )
    if not isinstance(data, dict):
        return None
    return _clamp_score(data.get("score"))


FIT_SCHEMA = {
    "type": "object",
    "properties": {
        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "flagged_skills": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fit_score", "summary"],
    "additionalProperties": False,
}


def extract_resume_text(profile, max_chars=None):
    """Cached plain text of a candidate's resume. Never raises.

    Thin wrapper around :mod:`assessments.resume` kept for callers that only
    have a profile; the text is cached on the profile itself.
    """
    from assessments import resume as resume_service

    try:
        text = resume_service.get_resume_text(profile)
    except Exception:  # pragma: no cover - best effort
        logger.warning(
            "Resume text unavailable for profile %s.", getattr(profile, "pk", "?"), exc_info=True
        )
        return ""
    return text[:max_chars] if max_chars else text


def _string_list(value, limit=8):
    """Coerce a model-supplied list into a short list of clean strings."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("name") or item.get("text") or item.get("skill") or ""
        text = str(item).strip()
        if text:
            out.append(text[:200])
        if len(out) >= limit:
            break
    return out


def summarize_fit(application):
    """Set ``ai_summary``/``ai_fit_score``/``ai_details``. Returns the score."""
    job = application.job
    profile = application.candidate
    prompt = SUMMARIZE_FIT_PROMPT.format(
        title=job.title,
        description=job.description or "",
        requirements=job.requirements or "",
        job_skills=", ".join(s.name for s in job.skills.all()) or "none listed",
        headline=getattr(profile, "headline", "") or "",
        experience_years=getattr(profile, "experience_years", "") or "",
        candidate_skills=", ".join(s.name for s in profile.skills.all()) or "none listed",
        notice_period_days=getattr(profile, "notice_period_days", 0),
        resume_text=extract_resume_text(profile) or "(no resume text available)",
    )
    data = _ask(prompt, schema=FIT_SCHEMA)
    if not isinstance(data, dict):
        return None
    score = _clamp_score(data.get("fit_score"))
    summary = str(data.get("summary") or "").strip()
    details = {
        "fit_score": score,
        "summary": summary,
        "strengths": _string_list(data.get("strengths")),
        "gaps": _string_list(data.get("gaps")),
        "flagged_skills": _string_list(data.get("flagged_skills")),
        "model": MODEL,
        "scored_at": timezone.now().isoformat(),
        "resume_text_used": bool(getattr(profile, "resume_text", "")),
    }
    application.ai_summary = summary
    application.ai_fit_score = score
    application.ai_details = details
    application.save(update_fields=["ai_summary", "ai_fit_score", "ai_details"])
    return score
