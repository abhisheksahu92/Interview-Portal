from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


def for_company(qs, company):
    """Scope a queryset to a company.

    Returns an empty queryset when ``company`` is None so a missing tenant can
    never leak another tenant's rows.
    """
    if company is None:
        return qs.none()
    return qs.filter(company=company)


class CompanyRequiredMixin(LoginRequiredMixin):
    """Login required plus an active tenant (``request.company``)."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and getattr(request, "company", None) is None:
            raise PermissionDenied("No company selected for this user.")
        return super().dispatch(request, *args, **kwargs)

    @property
    def company(self):
        return getattr(self.request, "company", None)


def role_required(*roles):
    """View decorator: require an authenticated user whose role in
    ``request.company`` is one of ``roles``.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                raise PermissionDenied("Authentication required.")
            company = getattr(request, "company", None)
            if company is None:
                raise PermissionDenied("No company selected for this user.")
            if user.role_in(company) not in roles:
                raise PermissionDenied("Insufficient role for this action.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
