"""Thin Anthropic wrapper for assessment/screening AI features.

Every public function degrades gracefully: with no ``ANTHROPIC_API_KEY`` (or on
any SDK/API/parse failure) it logs a warning and returns ``None``/``[]`` instead
of raising into a request.
"""

import json
import logging
import re

from django.conf import settings

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
Assess how well this candidate fits the role.

Job title: {title}
Job description:
{description}

Job requirements:
{requirements}

Required skills: {job_skills}

Candidate headline: {headline}
Candidate years of experience: {experience_years}
Candidate skills: {candidate_skills}
Notice period (days): {notice_period_days}
Resume text (may be empty):
{resume_text}

Return JSON: {{"fit_score": <integer 0-100>, "summary": "<3-5 sentence summary
covering strengths, gaps and a recommendation>"}}
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


def _ask(prompt):
    """Send one prompt and return the parsed JSON object, or ``None``."""
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
                difficulty=(
                    difficulty if difficulty in valid_difficulties else Question.MEDIUM
                ),
                source=Question.AI,
            )
        )
    return created


def grade_text_answer(question, answer):
    """Return an int 0-100 for a free-text answer, or ``None``."""
    if not answer:
        return None
    data = _ask(
        GRADE_TEXT_PROMPT.format(
            question=getattr(question, "text", str(question)), answer=answer
        )
    )
    if not isinstance(data, dict):
        return None
    return _clamp_score(data.get("score"))


def extract_resume_text(profile, max_chars=8000):
    """Best-effort plain text from a candidate's resume file. Never raises."""
    resume = getattr(profile, "resume", None)
    if not resume:
        return ""
    name = (getattr(resume, "name", "") or "").lower()
    try:
        with resume.open("rb") as handle:
            raw = handle.read(2_000_000)
    except Exception:
        logger.warning("Could not read resume file for profile %s.", getattr(profile, "pk", "?"))
        return ""
    if name.endswith(".pdf"):
        try:
            import io

            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text[:max_chars]
        except Exception:
            logger.info("PDF text extraction unavailable; skipping resume text.")
            return ""
    try:
        return raw.decode("utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def summarize_fit(application):
    """Set ``ai_summary``/``ai_fit_score`` on ``application``. Returns the score."""
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
        resume_text=extract_resume_text(profile),
    )
    data = _ask(prompt)
    if not isinstance(data, dict):
        return None
    score = _clamp_score(data.get("fit_score"))
    summary = str(data.get("summary") or "").strip()
    application.ai_summary = summary
    application.ai_fit_score = score
    application.save(update_fields=["ai_summary", "ai_fit_score"])
    return score
