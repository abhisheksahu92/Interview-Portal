"""Referral middleware.

Add to ``MIDDLEWARE`` in ``interview_portal/settings.py`` (one line, after
``SessionMiddleware``)::

    "partners.middleware.ReferralMiddleware",

It copies a ``?ref=`` query parameter or the ``ip_ref`` cookie into the session
and into a thread-local, so the ``Membership`` post_save signal can attach the
referral to a company created during this request.
"""

import threading

from partners.referral import capture_ref

_state = threading.local()


def current_ref():
    """The referral code captured for the request being handled, or None."""
    return getattr(_state, "ref", None)


def set_current_ref(code):
    _state.ref = code or None


def clear_current_ref():
    _state.ref = None


class ReferralMiddleware:
    """Make the active referral code visible to signals during this request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        code = capture_ref(request)
        set_current_ref(code)
        request.referral_code = code
        try:
            return self.get_response(request)
        finally:
            clear_current_ref()
