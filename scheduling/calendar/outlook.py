"""Outlook / Microsoft 365 calendar adapter.

Env-gated by ``settings.MS_OAUTH_CLIENT_ID`` / ``MS_OAUTH_CLIENT_SECRET``.
Uses MSAL for OAuth and Microsoft Graph over ``requests``; both are imported
lazily so an unconfigured deployment never needs them.
"""

from datetime import UTC, datetime
from urllib.parse import urlencode

from django.conf import settings

from scheduling.calendar.base import CalendarAdapter, NotConfigured

AUTHORITY = "https://login.microsoftonline.com/common"
GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["Calendars.ReadWrite"]


def _parse(value):
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class OutlookCalendarAdapter(CalendarAdapter):
    provider = "OUTLOOK"
    label = "Outlook Calendar"
    unconfigured_note = (
        "Outlook Calendar is not configured. Set MS_OAUTH_CLIENT_ID and "
        "MS_OAUTH_CLIENT_SECRET to enable it."
    )

    @classmethod
    def configured(cls) -> bool:
        return bool(
            getattr(settings, "MS_OAUTH_CLIENT_ID", "")
            and getattr(settings, "MS_OAUTH_CLIENT_SECRET", "")
        )

    def _app(self):
        import msal  # imported lazily

        return msal.ConfidentialClientApplication(
            settings.MS_OAUTH_CLIENT_ID,
            authority=AUTHORITY,
            client_credential=settings.MS_OAUTH_CLIENT_SECRET,
        )

    # -- OAuth -------------------------------------------------------------
    def authorize_url(self, redirect_uri, state):
        if not self.configured():
            raise NotConfigured(self.unconfigured_note)
        query = urlencode(
            {
                "client_id": settings.MS_OAUTH_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "response_mode": "query",
                "scope": " ".join(SCOPES),
                "state": state,
            }
        )
        return f"{AUTHORITY}/oauth2/v2.0/authorize?{query}"

    def exchange_code(self, code, redirect_uri, state=None):
        if not self.configured():
            raise NotConfigured(self.unconfigured_note)
        result = self._app().acquire_token_by_authorization_code(
            code, scopes=SCOPES, redirect_uri=redirect_uri
        )
        if not isinstance(result, dict) or "access_token" not in result:
            raise NotConfigured((result or {}).get("error_description", "Token exchange failed"))
        return {
            "token": result["access_token"],
            "refresh_token": result.get("refresh_token", ""),
            "scopes": SCOPES,
            "expires_in": result.get("expires_in"),
        }

    # -- Calendar ----------------------------------------------------------
    def _headers(self, connection):
        token = (connection.tokens or {}).get("token", "")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _request(self, method, path, connection, **kwargs):
        import requests  # imported lazily

        response = requests.request(
            method, f"{GRAPH}{path}", headers=self._headers(connection), timeout=15, **kwargs
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def busy(self, connection, start, end):
        if not self.configured() or not connection.is_live:
            return []
        payload = self._request(
            "GET",
            "/me/calendarView"
            f"?startDateTime={start.isoformat()}&endDateTime={end.isoformat()}"
            "&$select=start,end,showAs&$top=100",
            connection,
        )
        intervals = []
        for item in (payload or {}).get("value", []):
            if item.get("showAs") in {"free", "workingElsewhere"}:
                continue
            begin = _parse((item.get("start") or {}).get("dateTime"))
            finish = _parse((item.get("end") or {}).get("dateTime"))
            if begin and finish:
                intervals.append((begin, finish))
        return intervals

    @staticmethod
    def _body(event):
        return {
            "subject": event.summary,
            "body": {"contentType": "text", "content": event.description},
            "location": {"displayName": event.location},
            "start": {"dateTime": event.start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": event.end.isoformat(), "timeZone": "UTC"},
            "attendees": [
                {"emailAddress": {"address": email}, "type": "required"}
                for email in event.attendees
            ],
        }

    def create_event(self, connection, event):
        if not self.configured() or not connection.is_live:
            return None
        created = self._request("POST", "/me/events", connection, json=self._body(event))
        return (created or {}).get("id")

    def update_event(self, connection, event_id, event):
        if not self.configured() or not connection.is_live:
            return event_id
        updated = self._request(
            "PATCH", f"/me/events/{event_id}", connection, json=self._body(event)
        )
        return (updated or {}).get("id", event_id)

    def delete_event(self, connection, event_id):
        if not self.configured() or not connection.is_live:
            return None
        self._request("DELETE", f"/me/events/{event_id}", connection)
        return None
