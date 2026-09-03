"""Regex heuristics that pull contact details out of resume text.

Deliberately conservative: every helper returns ``""``/``None`` rather than
guessing wildly, because the AI extractor (``talent.ai``) and the recruiter both
get a chance to improve on the result.
"""

import os
import re

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
#: A run of digits with optional separators, e.g. "+91 98765 43210", "(020) 555-0134".
PHONE_RE = re.compile(r"(?<![\d@.])\+?\d(?:[\d\s().-]{5,17})\d(?![\d])")
EXPERIENCE_RE = re.compile(
    r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)(?:\s*(?:of|in))?\s*(?:experience|exp)?",
    re.IGNORECASE,
)
_NAME_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z.'\-]+){0,3}$")
_NAME_STOPWORDS = {
    "resume",
    "curriculum",
    "vitae",
    "cv",
    "profile",
    "summary",
    "objective",
    "contact",
    "address",
    "phone",
    "email",
    "skills",
    "experience",
    "education",
}


def find_email(text):
    """First email address in ``text``, lowercased."""
    match = EMAIL_RE.search(text or "")
    return match.group(0).lower() if match else ""


def find_phone(text):
    """First plausible phone number, normalised to digits (with leading +)."""
    for raw in PHONE_RE.findall(text or ""):
        digits = re.sub(r"[^\d+]", "", raw)
        core = digits.lstrip("+")
        if 7 <= len(core) <= 15:
            return digits[:30]
    return ""


def find_experience_years(text):
    """Largest "N years of experience" figure in ``text``, or None."""
    values = []
    for raw in EXPERIENCE_RE.findall(text or ""):
        try:
            value = float(raw)
        except ValueError:
            continue
        if 0 < value <= 60:
            values.append(value)
    return max(values) if values else None


def find_name(text, filename=""):
    """Guess the candidate name from the first usable line, else the filename."""
    for line in (text or "").splitlines()[:12]:
        line = line.strip().strip("|,-")
        if not (2 <= len(line) <= 60) or EMAIL_RE.search(line):
            continue
        words = line.split()
        if any(word.strip(".,").lower() in _NAME_STOPWORDS for word in words):
            continue
        if any(char.isdigit() for char in line):
            continue
        if _NAME_LINE_RE.match(line) and len(words) >= 2:
            return " ".join(word.capitalize() if word.isupper() else word for word in words)
    return name_from_filename(filename)


def name_from_filename(filename):
    """"asha_rao_resume.pdf" -> "Asha Rao"."""
    stem = os.path.splitext(os.path.basename(filename or ""))[0]
    stem = re.sub(r"(?i)\b(resume|cv|profile|final|updated|copy|\d+)\b", " ", stem)
    words = [w for w in re.split(r"[\s_.\-]+", stem) if w]
    return " ".join(w.capitalize() for w in words)[:150]


def parse_resume_text(text, filename=""):
    """Extract a best-effort ``{name, email, phone, experience_years}`` dict."""
    text = text or ""
    return {
        "name": find_name(text, filename),
        "email": find_email(text),
        "phone": find_phone(text),
        "experience_years": find_experience_years(text),
    }


def split_skills(value):
    """Split a free-form skills string/list into a clean list of names."""
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        items = [str(v) for v in value]
    else:
        items = re.split(r"[,;/|\n]+", str(value))
    seen, out = set(), []
    for item in items:
        item = re.sub(r"\s+", " ", item).strip(" .")
        if not item or len(item) > 80:
            continue
        if item.lower() in seen:
            continue
        seen.add(item.lower())
        out.append(item)
    return out
