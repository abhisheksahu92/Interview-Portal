"""Reddit hiring subreddits, via an OAuth client-credentials app.

Reddit blocks anonymous JSON from server IPs, so this adapter needs an app.
Without ``REDDIT_CLIENT_ID``/``REDDIT_CLIENT_SECRET`` it reports itself as
unavailable and the runner marks the source SKIPPED rather than failing.
"""

import base64
import urllib.parse

from django.conf import settings

from sources.adapters.base import Adapter, RawItem, parse_dt, snippet_of
from sources.http import get, get_json

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
LISTING = "https://oauth.reddit.com/r/{subreddit}/new?limit=50"
DEFAULT_SUBREDDITS = ["forhire", "hiring", "remotejs"]

#: Flair/title markers that mean the poster wants to be hired, not hire.
SEEKING_MARKERS = ("[for hire]", "[task]")


def credentials():
    return (
        (getattr(settings, "REDDIT_CLIENT_ID", "") or "").strip(),
        (getattr(settings, "REDDIT_CLIENT_SECRET", "") or "").strip(),
    )


class RedditAdapter(Adapter):
    slug = "reddit"
    name = "Reddit hiring subreddits"
    kind = "API"

    def available(self):
        return all(credentials())

    def token(self):
        client_id, secret = credentials()
        basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
        payload = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        response = get(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=payload,
        )
        import json

        return json.loads(response).get("access_token", "")

    def fetch(self, source):
        access_token = self.token()
        headers = {"Authorization": f"bearer {access_token}"}
        for subreddit in source.config.get("subreddits") or DEFAULT_SUBREDDITS:
            payload = get_json(LISTING.format(subreddit=subreddit), headers=headers)
            yield from self.parse(payload)

    def parse(self, payload):
        for child in (payload.get("data") or {}).get("children") or []:
            post = child.get("data") or {}
            title = post.get("title") or ""
            lowered = title.lower()
            if any(marker in lowered for marker in SEEKING_MARKERS):
                continue  # people offering themselves, not offering work
            yield RawItem(
                external_id=str(post.get("id") or ""),
                kind="FREELANCE" if "hiring" in lowered else "GIG",
                title=title[:300],
                url="https://www.reddit.com" + (post.get("permalink") or ""),
                company_name=post.get("author") or "",
                snippet=snippet_of(post.get("selftext")),
                remote=True,
                tags=[str(post.get("subreddit") or "").lower()],
                posted_at=parse_dt(post.get("created_utc")),
            )
