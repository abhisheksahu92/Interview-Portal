"""Google Calendar adapter.

Env-gated by ``settings.GOOGLE_OAUTH_CLIENT_ID`` / ``GOOGLE_OAUTH_CLIENT_SECRET``.
The Google SDKs are imported lazily inside the methods so the app (and the test
suite) works fine when ``google-api-python-client`` is absent or unconfigured.
"""

from datetime import UTC, datetime

from django.conf import settings

from scheduling.calendar.base import CalendarAdapter, NotConfigured

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def _parse(value):
    """Parse a Google RFC-3339 timestamp into an aware UTC datetime."""
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class GoogleCalendarAdapter(CalendarAdapter):
    provider = "GOOGLE"
    label = "Google Calendar"
    unconfigured_note = (
        "Google Calendar is not configured. Set GOOGLE_OAUTH_CLIENT_ID and "
        "GOOGLE_OAUTH_CLIENT_SECRET to enable it."
    )

    @classmethod
    def configured(cls) -> bool:
        return bool(
            getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
            and getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "")
        )

    @classmethod
    def client_config(cls, redirect_uri):
        return {
            "web": {
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "auth_uri": AUTH_URI,
                "token_uri": TOKEN_URI,
                "redirect_uris": [redirect_uri],
            }
        }

    # -- OAuth -------------------------------------------------------------
    def _flow(self, redirect_uri, state=None):
        from google_auth_oauthlib.flow import Flow  # imported lazily

        return Flow.from_client_config(
            self.client_config(redirect_uri), scopes=SCOPES, state=state,
            redirect_uri=redirect_uri,
        )

    def authorize_url(self, redirect_uri, state):
        if not self.configured():
            raise NotConfigured(self.unconfigured_note)
        url, _ = self._flow(redirect_uri, state).authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent"
        )
        return url

    def exchange_code(self, code, redirect_uri, state=None):
        if not self.configured():
            raise NotConfigured(self.unconfigured_note)
        flow = self._flow(redirect_uri, state)
        flow.fetch_token(code=code)
        creds = flow.credentials
        return {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "scopes": list(creds.scopes or SCOPES),
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }

    # -- Calendar ----------------------------------------------------------
    def _service(self, connection):
        from google.oauth2.credentials import Credentials  # imported lazily
        from googleapiclient.discovery import build

        tokens = connection.tokens or {}
        creds = Credentials(
            token=tokens.get("token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=tokens.get("token_uri", TOKEN_URI),
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            scopes=tokens.get("scopes", SCOPES),
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def busy(self, connection, start, end):
        if not self.configured() or not connection.is_live:
            return []
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "items": [{"id": "primary"}],
        }
        response = self._service(connection).freebusy().query(body=body).execute()
        calendars = (response or {}).get("calendars", {})
        intervals = []
        for calendar in calendars.values():
            for block in calendar.get("busy", []):
                begin, finish = _parse(block.get("start")), _parse(block.get("end"))
                if begin and finish:
                    intervals.append((begin, finish))
        return intervals

    @staticmethod
    def _body(event):
        return {
            "summary": event.summary,
            "description": event.description,
            "location": event.location,
            "start": {"dateTime": event.start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": event.end.isoformat(), "timeZone": "UTC"},
            "attendees": [{"email": email} for email in event.attendees],
        }

    def create_event(self, connection, event):
        if not self.configured() or not connection.is_live:
            return None
        created = (
            self._service(connection)
            .events()
            .insert(calendarId="primary", body=self._body(event))
            .execute()
        )
        return (created or {}).get("id")

    def update_event(self, connection, event_id, event):
        if not self.configured() or not connection.is_live:
            return event_id
        updated = (
            self._service(connection)
            .events()
            .update(calendarId="primary", eventId=event_id, body=self._body(event))
            .execute()
        )
        return (updated or {}).get("id", event_id)

    def delete_event(self, connection, event_id):
        if not self.configured() or not connection.is_live:
            return None
        self._service(connection).events().delete(
            calendarId="primary", eventId=event_id
        ).execute()
        return None
