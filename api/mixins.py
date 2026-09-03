"""Shared viewset behaviour: tenant resolution and query scoping."""

from rest_framework.exceptions import PermissionDenied

from core.models import Company

COMPANY_HEADER = "X-Company"


class CompanyScopedViewSetMixin:
    """Resolve the active company and scope every queryset to it.

    Resolution order: ``X-Company`` header (company slug, validated against the
    user's memberships) -> ``request.company`` from TenantMiddleware -> the
    user's first membership. Token-auth clients have no session, so the header
    is the supported way to pick a tenant.
    """

    #: dotted lookup from the model to its company, e.g. "job__company".
    company_field = "company"

    @property
    def company(self):
        if not hasattr(self, "_company"):
            self._company = self.resolve_company()
        return self._company

    def resolve_company(self):
        request = self.request
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        slug = request.headers.get(COMPANY_HEADER)
        if slug:
            company = Company.objects.filter(
                slug=slug, memberships__user=user
            ).first()
            if company is None:
                raise PermissionDenied(f"No membership in company '{slug}'.")
            return company

        company = getattr(request, "company", None)
        if company is not None and user.membership_for(company) is not None:
            return company

        membership = user.memberships.select_related("company").first()
        return membership.company if membership else None

    def scope_queryset(self, qs):
        company = self.company
        if company is None:
            return qs.none()
        return qs.filter(**{self.company_field: company})

    def get_queryset(self):
        return self.scope_queryset(super().get_queryset())

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["company"] = self.company
        return context
