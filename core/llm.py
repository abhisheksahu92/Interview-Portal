"""One place that talks to a language model.

KAN-9: AI Provider Gateway with circuit-breaker fallback chain.

Provider priority (first non-cooling-down provider with a key wins):
  1. Anthropic  – production-tuned prompts, highest quality
  2. Gemini     – backup cloud provider
  3. Ollama     – local fallback (always available when running locally)

Circuit breaker: on HTTP 429 / 503 / 504 a provider is marked cooling-down
in Django's cache (Redis in prod, LocMem in tests) for an exponentially
growing cooldown period. Subsequent calls skip that provider and try the
next one in the chain.

Public API (unchanged):
  active_provider() → str or ""
  is_configured()   → bool
  complete(prompt, *, system, max_tokens, schema, model) → str | None
"""

import json
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GEMINI_RETRIES = 3
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
)

OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"
OLLAMA_DEFAULT_MODEL = "qwen2.5-coder:7b"

# How long to cool down a provider after a rate-limit / server error (seconds).
# We use a simple fixed window; callers that want exponential backoff can
# call _mark_provider_cooling_down with a longer duration on repeated errors.
_COOLDOWN_BASE = 60  # seconds

# Cache key template
_COOLDOWN_KEY = "llm_cooldown:{provider}"

# Provider chain in priority order
_PROVIDER_CHAIN = ["anthropic", "gemini", "ollama"]


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------


def _anthropic_key():
    return (getattr(settings, "ANTHROPIC_API_KEY", "") or "").strip()


def _gemini_key():
    return (getattr(settings, "GEMINI_API_KEY", "") or "").strip()


def _ollama_enabled():
    """Ollama is always available as a local fallback; can be disabled via settings."""
    return getattr(settings, "OLLAMA_ENABLED", True)


# ---------------------------------------------------------------------------
# Circuit-breaker helpers
# ---------------------------------------------------------------------------


def _is_provider_cooling_down(name: str) -> bool:
    """Return True if this provider is in the cooling-down window."""
    return bool(cache.get(_COOLDOWN_KEY.format(provider=name)))


def _mark_provider_cooling_down(name: str, seconds: int = _COOLDOWN_BASE) -> None:
    """Mark a provider as unavailable for *seconds*."""
    cache.set(_COOLDOWN_KEY.format(provider=name), 1, seconds)
    logger.warning("llm_gateway: provider=%s cooling_down_for=%ds", name, seconds)


def _clear_provider_cooldown(name: str) -> None:
    """Remove a cooldown (e.g. after a successful call)."""
    cache.delete(_COOLDOWN_KEY.format(provider=name))


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


def _provider_has_key(name: str) -> bool:
    if name == "anthropic":
        return bool(_anthropic_key())
    if name == "gemini":
        return bool(_gemini_key())
    if name == "ollama":
        return _ollama_enabled()
    return False


def active_provider() -> str:
    """Return the first provider that is configured AND not cooling down.

    Returns empty string when no provider is usable.
    """
    for name in _PROVIDER_CHAIN:
        if _provider_has_key(name) and not _is_provider_cooling_down(name):
            return name
    return ""


def is_configured() -> bool:
    return bool(active_provider())


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------


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
    except Exception as exc:
        # Check for rate-limit / server errors and signal them upward
        exc_str = str(exc).lower()
        if any(code in exc_str for code in ("429", "rate", "overloaded", "503", "504")):
            raise _ProviderRateLimited("anthropic") from exc
        logger.exception("Anthropic request failed.")
        return None


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------


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
            if exc.code in (429, 503, 504):
                raise _ProviderRateLimited("gemini") from exc
            if exc.code in (500, 502) and attempt < GEMINI_RETRIES:
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
        logger.warning("Gemini returned no usable text.")
        return None


# ---------------------------------------------------------------------------
# Ollama backend (local fallback)
# ---------------------------------------------------------------------------


def _complete_ollama(system, prompt, max_tokens, model):
    """Call a local Ollama model. Returns text or None; never raises."""
    ollama_model = model or OLLAMA_DEFAULT_MODEL
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    body = {
        "model": ollama_model,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.2,
        },
    }
    request = urllib.request.Request(
        OLLAMA_ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.load(response)
        text = payload.get("response", "")
        # Strip <think>…</think> blocks from reasoning models
        import re
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return text or None
    except Exception:
        logger.exception("Ollama request failed (model=%s).", ollama_model)
        return None


# ---------------------------------------------------------------------------
# Internal sentinel for rate-limit signalling
# ---------------------------------------------------------------------------


class _ProviderRateLimited(Exception):
    """Raised internally when a provider signals rate-limiting or overload."""
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        super().__init__(provider_name)


# ---------------------------------------------------------------------------
# Gateway entry point
# ---------------------------------------------------------------------------


def complete(prompt, *, system="", max_tokens=1024, schema=None, model=""):
    """Return the model's text, or ``None`` if all providers failed or none are configured.

    Tries each provider in the chain (anthropic → gemini → ollama).
    On rate-limit / server overload: marks that provider cooling-down in cache,
    then immediately tries the next one.
    """
    tried = []
    for provider_name in _PROVIDER_CHAIN:
        if not _provider_has_key(provider_name):
            continue
        if _is_provider_cooling_down(provider_name):
            logger.debug("llm_gateway: skipping provider=%s (cooling down)", provider_name)
            continue

        tried.append(provider_name)
        t0 = time.monotonic()
        try:
            if provider_name == "anthropic":
                result = _complete_anthropic(system, prompt, max_tokens, schema, model)
            elif provider_name == "gemini":
                result = _complete_gemini(system, prompt, max_tokens, schema, model)
            else:  # ollama
                result = _complete_ollama(system, prompt, max_tokens, model)

            latency_ms = int((time.monotonic() - t0) * 1000)
            if result is not None:
                _clear_provider_cooldown(provider_name)
                logger.info(
                    "llm_gateway: provider=%s latency_ms=%d tried=%s",
                    provider_name,
                    latency_ms,
                    tried,
                )
                return result
            # Provider returned None without raising (e.g. empty response / safety block)
            logger.warning(
                "llm_gateway: provider=%s returned None; trying next", provider_name
            )
        except _ProviderRateLimited as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            _mark_provider_cooling_down(exc.provider_name, _COOLDOWN_BASE)
            logger.warning(
                "llm_gateway: provider=%s rate_limited latency_ms=%d; trying next",
                exc.provider_name,
                latency_ms,
            )
        except Exception:
            latency_ms = int((time.monotonic() - t0) * 1000)
            logger.exception(
                "llm_gateway: provider=%s unexpected error latency_ms=%d; trying next",
                provider_name,
                latency_ms,
            )

    logger.warning(
        "llm_gateway: all providers exhausted tried=%s; returning None", tried or ["none"]
    )
    return None
