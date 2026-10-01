"""Slack messaging helper for Interview Portal alerts, signups, and events."""

import json
import logging
from urllib.error import HTTPError
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def send_slack_message(channel_key_or_id: str, text: str, blocks: list = None) -> bool:
    """Send a message to a Slack channel using the bot token.

    Args:
        channel_key_or_id: Key from settings.SLACK_CHANNELS (e.g. 'alerts', 'signups', 'payments')
                           or raw Slack channel ID (e.g. 'C0C5AGMH4KH').
        text: Plain-text fallback for notification previews.
        blocks: Optional Block Kit structure.

    Returns:
        bool: True if delivered successfully, False otherwise.
    """
    token = getattr(settings, "SLACK_BOT_TOKEN", None)
    if not token:
        logger.debug("SLACK_BOT_TOKEN is not configured; skipping Slack dispatch.")
        return False

    channel_id = getattr(settings, "SLACK_CHANNELS", {}).get(channel_key_or_id, channel_key_or_id)
    if not channel_id:
        logger.warning("No channel ID resolved for Slack channel key: %s", channel_key_or_id)
        return False

    payload = {
        "channel": channel_id,
        "text": text,
    }
    if blocks:
        payload["blocks"] = blocks

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode("utf-8"))
            if not res.get("ok"):
                logger.warning("Slack message send failed to %s: %s", channel_key_or_id, res.get("error"))
                return False
            return True
    except (HTTPError, OSError) as exc:
        logger.exception("Slack network/HTTP error sending message to %s: %s", channel_key_or_id, exc)
        return False
