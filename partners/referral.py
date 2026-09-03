"""Referral capture: ``?ref=CODE`` -> cookie -> session -> Referral row.

Flow:

1. ``/partners/r/<code>/`` (:func:`partners.views.referral_link`) sets the
   30-day ``ip_ref`` cookie and redirects to company signup.
2. :class:`partners.middleware.ReferralMiddleware` copies that cookie into the
   session (and into a thread-local) on every request.
3. When a company signup creates the OWNER membership, the
   :mod:`partners.signals` receiver attaches the referral to the new company.
"""

COOKIE_NAME = "ip_ref"
SESSION_KEY = "ip_ref"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def set_ref_cookie(response, code):
    """Store ``code`` on ``response`` as the 30-day referral cookie."""
    response.set_cookie(
        COOKIE_NAME,
        code,
        max_age=COOKIE_MAX_AGE,
        samesite="Lax",
        httponly=True,
    )
    return response


def capture_ref(request):
    """Resolve the referral code for this request and remember it in the session.

    Looks at ``?ref=``, then the ``ip_ref`` cookie, then the session. Returns
    the code (lower-cased) or None.
    """
    code = (request.GET.get("ref") or "").strip().lower()
    if not code:
        code = (request.COOKIES.get(COOKIE_NAME) or "").strip().lower()
    session = getattr(request, "session", None)
    if not code and session is not None:
        code = (session.get(SESSION_KEY) or "").strip().lower()
    if code and session is not None and session.get(SESSION_KEY) != code:
        session[SESSION_KEY] = code
    return code or None


def attach_referral(company, request=None, code=None):
    """Create the :class:`~partners.models.Referral` for ``company``, if any.

    Returns the Referral, or None when there is no code, no active reseller
    with that code, or the company already has a referral.
    """
    from partners.models import Referral, Reseller

    if company is None:
        return None
    if code is None and request is not None:
        code = capture_ref(request)
    if code is None:
        from partners.middleware import current_ref

        code = current_ref()
    if not code:
        return None
    reseller = Reseller.objects.filter(code=code.strip().lower(), active=True).first()
    if reseller is None:
        return None
    referral, _ = Referral.objects.get_or_create(
        company=company, defaults={"reseller": reseller}
    )
    return referral
