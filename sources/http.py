"""The only place in this app that touches the network.

Every feed is public and none of them owe us anything, so the rules live here
rather than in fifteen adapters: a descriptive User-Agent that identifies us, a
hard timeout, a per-host rate limit, and a robots.txt check for anything that
is not a documented JSON API. Tests never reach this module — adapters parse
recorded fixtures.
"""

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
import urllib.robotparser

logger = logging.getLogger(__name__)

USER_AGENT = "InterviewPortal/0.1 (job aggregator)"
TIMEOUT = 30
#: Minimum gap between two requests to the same host.
RATE_LIMIT_SECONDS = 1.0
#: Ashby boards can be many megabytes; nothing needs more than this.
MAX_BYTES = 8 * 1024 * 1024

_lock = threading.Lock()
_last_call = {}
_robots = {}


class FetchError(RuntimeError):
    """Any upstream failure. Adapters let it out; the runner records it."""


def _throttle(host):
    with _lock:
        wait = RATE_LIMIT_SECONDS - (time.monotonic() - _last_call.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.monotonic()


def robots_allows(url):
    """True unless the host's robots.txt says no. Unreachable robots = allowed."""
    parts = urllib.parse.urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}"
    parser = _robots.get(root)
    if parser is None:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(root + "/robots.txt")
        try:
            parser.read()
        except Exception:
            # A missing or broken robots.txt is not a prohibition.
            parser.allow_all = True
        _robots[root] = parser
    try:
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def get(url, *, headers=None, timeout=TIMEOUT, check_robots=False, data=None):
    """Fetch bytes, or raise :class:`FetchError`."""
    if check_robots and not robots_allows(url):
        raise FetchError(f"robots.txt disallows {url}")
    _throttle(urllib.parse.urlsplit(url).netloc)
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(MAX_BYTES)
    except Exception as exc:  # urllib raises a whole family of these
        raise FetchError(f"{url}: {exc}") from exc


def get_json(url, **kwargs):
    raw = get(url, **kwargs)
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise FetchError(f"{url}: response was not JSON") from exc
