from core.models import Company


class TenantMiddleware:
    """Attach the active tenant to every request as ``request.company``.

    Resolution order: session ``company_id`` -> user's first membership -> None.
    """

    session_key = "company_id"

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
            company = Company.objects.filter(
                id=company_id, memberships__user=user
            ).first()
            if company is not None:
                return company
            request.session.pop(self.session_key, None)

        membership = user.memberships.select_related("company").first()
        if membership is None:
            return None
        request.session[self.session_key] = membership.company_id
        return membership.company
