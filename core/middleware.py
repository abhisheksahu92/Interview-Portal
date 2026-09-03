from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse

from core.models import Company

SESSION_COMPANY_KEY = "company_id"


def login_url():
    url = settings.LOGIN_URL
    return url if url.startswith("/") else reverse(url)


def set_active_company(request, company):
    """Make ``company`` the active tenant for this session and remember it."""
    if company is None:
        return None
    request.session[SESSION_COMPANY_KEY] = company.pk
    request.company = company
    user = getattr(request, "user", None)
    if (
        user is not None
        and user.is_authenticated
        and getattr(user, "last_company_id", None) != company.pk
    ):
        user.last_company_id = company.pk
        user.save(update_fields=["last_company"])
    return company


class TenantMiddleware:
    """Attach the active tenant to every request as ``request.company``.

    Resolution order: session ``company_id`` -> ``user.last_company`` ->
    the user's first membership -> None.
    """

    session_key = SESSION_COMPANY_KEY

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.company = self.resolve_company(request)
        return self.get_response(request)

    def resolve_company(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        company_id = request.session.get(self.session_key)
        if company_id:
            company = self._member_company(user, company_id)
            if company is not None:
                return company
            request.session.pop(self.session_key, None)

        # Restore the workspace this user last used (survives logout/login).
        if user.last_company_id:
            company = self._member_company(user, user.last_company_id)
            if company is not None:
                request.session[self.session_key] = company.pk
                return company

        membership = user.memberships.select_related("company").first()
        if membership is None:
            return None
        return set_active_company(request, membership.company)

    @staticmethod
    def _member_company(user, company_id):
        return Company.objects.filter(id=company_id, memberships__user=user).first()


class HtmxRedirectMiddleware:
    """Make HTMX requests survive an expired session.

    htmx swaps whatever the response body is, so a plain 302 to the login page
    would inject the login form into a fragment. For ``HX-Request`` responses
    that redirect to ``LOGIN_URL`` we answer 204 with an ``HX-Redirect`` header
    instead, which tells htmx to do a full-page navigation.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.headers.get("HX-Request") != "true":
            return response
        if response.status_code in (301, 302, 303, 307, 308):
            target = response.headers.get("Location", "")
            if target.split("?")[0] == login_url():
                return self._hx_redirect(target)
        return response

    @staticmethod
    def _hx_redirect(target):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = target
        return response
