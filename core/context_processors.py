def tenant(request):
    """Expose the active company and the user's role in it to templates."""
    company = getattr(request, "company", None)
    user = getattr(request, "user", None)
    role = user.role_in(company) if (user is not None and user.is_authenticated) else None
    companies = list(user.companies) if (user is not None and user.is_authenticated) else []
    return {
        "current_company": company,
        "current_role": role,
        "user_companies": companies,
    }
