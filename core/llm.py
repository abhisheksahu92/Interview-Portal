"""One place that talks to a language model.

Screening, grading, resume extraction and video review each used to build their
own Anthropic client. That made the provider a hard dependency: with no
ANTHROPIC_API_KEY every AI feature was simply off, which is most of what the
product charges for.

This module keeps the same contract those callers already relied on - return
text, or ``None`` on any failure, never raise - and lets a Gemini key stand in
when there is no Anthropic key. Anthropic wins when both are set, since the
prompts were written and tuned against it.
"""

import json
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

GEMINI_RETRIES = 3

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
)


def _anthropic_key():
    return (getattr(settings, "ANTHROPIC_API_KEY", "") or "").strip()


def _gemini_key():
    return (getattr(settings, "GEMINI_API_KEY", "") or "").strip()


def active_provider():
    """``"anthropic"``, ``"gemini"`` or ``""`` when nothing is configured."""
    if _anthropic_key():
        return "anthropic"
    if _gemini_key():
        return "gemini"
    return ""


def is_configured():
    return bool(active_provider())


def _anthropic_client():
    """Build the SDK client. Separate so tests can substitute a fake."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is pinned
        logger.warning("anthropic SDK is not installed; skipping that provider.")
        return None
    try:
        return anthropic.Anthropic(api_key=_anthropic_key())
    except Exception:
        logger.exception("Could not build the Anthropic client.")
        return None


def _complete_anthropic(system, prompt, max_tokens, schema, model):
    client = _anthropic_client()
    if client is None:
        return None

    extra = {}
    if schema is not None and hasattr(getattr(client, "messages", None), "parse"):
        extra["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
    try:
        response = client.messages.create(
            model=model or getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-5"),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            **extra,
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
    except Exception:
        logger.exception("Anthropic request failed.")
        return None


def _complete_gemini(system, prompt, max_tokens, schema, model):
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.2,
            # Gemini 2.5 spends output tokens on internal thinking before it
            # answers, and that comes out of maxOutputTokens: a grading call
            # burned 345 thinking tokens and returned truncated JSON that would
            # not parse. These are extraction tasks, not reasoning ones, so
            # turn thinking off - it also removes the latency and the cost.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    if schema is not None:
        # Ask for JSON but not a strict schema: the schemas here were written for
        # Anthropic and Gemini rejects constructs it does not share. Callers all
        # parse tolerantly anyway.
        body["generationConfig"]["responseMimeType"] = "application/json"

    url = GEMINI_ENDPOINT.format(
        model=model or getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
        key=_gemini_key(),
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    payload = None
    for attempt in range(GEMINI_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            # 429 is routine on the free tier when a batch job fans out; 5xx is
            # transient. Back off and retry rather than dropping the whole batch.
            if exc.code in (429, 500, 502, 503, 504) and attempt < GEMINI_RETRIES:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if (retry_after or "").isdigit() else 2.0 * (2**attempt)
                logger.info("Gemini HTTP %s; retrying in %.0fs", exc.code, delay)
                time.sleep(min(delay, 30))
                continue
            logger.warning("Gemini request failed: HTTP %s %s", exc.code, exc.reason)
            return None
        except Exception:
            logger.exception("Gemini request failed.")
            return None
    if payload is None:
        return None

    try:
        parts = payload["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
    except (KeyError, IndexError, TypeError):
        # A safety block or an empty candidate list lands here.
        logger.warning("Gemini returned no usable text.")
        return None


def complete(prompt, *, system="", max_tokens=1024, schema=None, model=""):
    """Return the model's text, or ``None`` if unconfigured or the call failed."""
    provider = active_provider()
    if not provider:
        logger.warning(
            "No LLM key set (ANTHROPIC_API_KEY or GEMINI_API_KEY); AI features are disabled."
        )
        return None
    if provider == "anthropic":
        return _complete_anthropic(system, prompt, max_tokens, schema, model)
    return _complete_gemini(system, prompt, max_tokens, schema, model)
