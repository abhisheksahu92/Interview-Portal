"""One implementation of "a secret link in a URL", shared by every app.

Several features hand out an unguessable URL — team invitations
(:class:`core.models.Invitation`), client-portal magic links
(:class:`clients.models.ClientAccess`), interview booking links and offer
signing links. They all need the same four things: generate a token, expire it,
revoke it, and record when it was last opened. This module is the single place
those live.

Usage::

    class Thing(TokenMixin, models.Model):
        EXPIRY_DAYS = 14

    resolution = resolve_token(Thing, token_from_url)
    if not resolution.ok:
        return token_invalid_response(request, resolution)

Status codes are deliberately *not* decided here — see
:func:`token_invalid_response`; callers pass ``status=`` when an existing
contract differs from the defaults (the invite-accept view answers 400, for
example). See the "Tokens" section of ARCHITECTURE.md.
"""

import enum
import secrets
from datetime import timedelta

from django.db import models
from django.shortcuts import render
from django.utils import timezone

DEFAULT_TOKEN_BYTES = 32


def generate_token(nbytes: int = DEFAULT_TOKEN_BYTES) -> str:
    """A URL-safe, unguessable token of roughly ``nbytes`` entropy."""
    return secrets.token_urlsafe(nbytes)


def default_expiry(days):
    """``days`` from now, or ``None`` when ``days`` is ``None`` (never expires)."""
    if days is None:
        return None
    return timezone.now() + timedelta(days=days)


class TokenState(enum.Enum):
    """Why a tokenised link is (or is not) usable."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    UNKNOWN = "unknown"

    @property
    def ok(self):
        return self is TokenState.ACTIVE

    @property
    def default_status(self):
        """The HTTP status a view should use for this state.

        Unknown tokens are 404 (there is nothing here); a link that *did* exist
        and has since expired or been revoked is 410 Gone.
        """
        if self is TokenState.UNKNOWN:
            return 404
        if self is TokenState.ACTIVE:
            return 200
        return 410


#: Human wording per state, used by ``core/token_invalid.html``.
STATE_REASONS = {
    TokenState.EXPIRED: "This link has expired.",
    TokenState.REVOKED: "This link was revoked.",
    TokenState.UNKNOWN: "This link is not valid.",
}


class TokenMixin(models.Model):
    """Abstract model giving a row a token, an expiry, a revocation and a
    "last opened" stamp.

    Subclasses own the *semantic* completion field (``accepted_at`` on an
    invitation, ``signed_at`` on an offer) and should override
    :attr:`token_status` if that field must show in the UI.
    """

    #: Default lifetime for :meth:`rotate`; ``None`` means "no expiry".
    EXPIRY_DAYS = None
    #: Entropy used by :meth:`new_token`.
    TOKEN_BYTES = DEFAULT_TOKEN_BYTES

    token = models.CharField(max_length=100, unique=True, default=generate_token)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    # -- creation ---------------------------------------------------------- #

    @classmethod
    def new_token(cls):
        return generate_token(cls.TOKEN_BYTES)

    @classmethod
    def default_expiry(cls, days=None):
        return default_expiry(cls.EXPIRY_DAYS if days is None else days)

    # -- state ------------------------------------------------------------- #

    @property
    def is_expired(self):
        return self.expires_at is not None and self.expires_at <= timezone.now()

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def is_active(self):
        return not self.is_revoked and not self.is_expired

    @property
    def token_state(self):
        if self.is_revoked:
            return TokenState.REVOKED
        if self.is_expired:
            return TokenState.EXPIRED
        return TokenState.ACTIVE

    # -- UI helpers (used by core/_access_links_table.html) ----------------- #

    @property
    def token_status_label(self):
        return self.token_state.value.title()

    @property
    def token_status_kind(self):
        """Badge modifier: ``accent`` / ``neutral`` / ``danger``."""
        return {
            TokenState.ACTIVE: "accent",
            TokenState.EXPIRED: "danger",
            TokenState.REVOKED: "neutral",
        }.get(self.token_state, "neutral")

    @property
    def link_purpose(self):
        """Short "what is this link for" column value."""
        return self._meta.verbose_name.title()

    # -- transitions -------------------------------------------------------- #

    def revoke(self):
        """Kill the link. Idempotent — an earlier revocation time is kept."""
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])
        return self

    def rotate(self, days=None):
        """Issue a fresh token and expiry on the same row, un-revoking it.

        This is what "resend the link" does: the old URL stops working.
        """
        self.token = self.new_token()
        self.revoked_at = None
        self.expires_at = self.default_expiry(days)
        self.save(update_fields=["token", "revoked_at", "expires_at"])
        return self

    def touch(self):
        """Record that the link was just opened."""
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])
        return self


class TokenResolution:
    """The outcome of :func:`resolve_token`: a row (maybe ``None``) + a state."""

    __slots__ = ("obj", "state")

    def __init__(self, obj, state):
        self.obj = obj
        self.state = state

    @property
    def ok(self):
        return self.state.ok

    @property
    def status_code(self):
        return self.state.default_status

    @property
    def reason(self):
        return STATE_REASONS.get(self.state, STATE_REASONS[TokenState.UNKNOWN])

    def __bool__(self):
        return self.ok

    def __iter__(self):
        """Allow ``obj, state = resolve_token(...)``."""
        return iter((self.obj, self.state))

    def __repr__(self):
        return f"<TokenResolution {self.state.name} obj={self.obj!r}>"


def resolve_token(model, token, *, queryset=None, select_related=()):
    """Look ``token`` up on ``model`` and classify it.

    Never raises for a bad token: the caller decides between 404, 410 and (for
    legacy contracts) 400 by reading :attr:`TokenResolution.state`.
    """
    qs = model._default_manager.all() if queryset is None else queryset
    if select_related:
        qs = qs.select_related(*select_related)
    obj = qs.filter(token=token).first() if token else None
    if obj is None:
        return TokenResolution(None, TokenState.UNKNOWN)
    return TokenResolution(obj, obj.token_state)


def token_invalid_response(
    request,
    resolution,
    *,
    status=None,
    template="core/token_invalid.html",
    context=None,
):
    """Render the shared "this link can't be used" page.

    ``status`` defaults to :attr:`TokenState.default_status`; pass it explicitly
    where an app already promised something else.
    """
    state = resolution.state if isinstance(resolution, TokenResolution) else resolution
    reason = STATE_REASONS.get(state, STATE_REASONS[TokenState.UNKNOWN])
    payload = {
        "token_state": state.value,
        "reason": reason,
        "contact_hint": "Ask whoever sent you this link for a fresh one.",
    }
    payload.update(context or {})
    return render(
        request,
        template,
        payload,
        status=status or state.default_status,
    )
