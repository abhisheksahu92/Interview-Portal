"""Safe rendering of recruiter-authored ``CareersSite.about`` text.

No HTML is ever trusted: the source is escaped first, then a tiny subset of
Markdown-ish structure (blank-line paragraphs and ``- `` bullets) is rebuilt
from the escaped text. That makes tag injection impossible by construction, so
no sanitiser dependency is needed.
"""

from django.utils.html import escape
from django.utils.safestring import mark_safe


def render_about(text):
    """Escape ``text`` and rebuild paragraphs / unordered lists as safe HTML."""
    if not text:
        return ""
    out, bullets = [], []

    def flush():
        if bullets:
            items = "".join(f"<li>{b}</li>" for b in bullets)
            out.append(f"<ul>{items}</ul>")
            bullets.clear()

    for block in escape(text).replace("\r\n", "\n").split("\n\n"):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        for line in lines:
            if line.startswith(("- ", "* ")):
                bullets.append(line[2:].strip())
            else:
                flush()
                out.append(f"<p>{line}</p>")
        flush()
    return mark_safe("".join(out))  # noqa: S308 - every fragment is escaped above
