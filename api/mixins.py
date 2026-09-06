"""Shared viewset behaviour: tenant resolution and query scoping."""

from django.core.exceptions import FieldDoesNotExist
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import PermissionDenied

from core.models import Company

COMPANY_HEADER = "X-Company"


def _company_path(model):
    """How to reach the owning company from ``model``, or None if it is shared.

    Some models hold the FK directly (Question.company); others reach it
    through their parent (PipelineStage -> job -> company).
    """
    for path, first in (("company", "company"), ("job__company", "job")):
        try:
            model._meta.get_field(first)
        except FieldDoesNotExist:
            continue
        return path
    return None


def scope_related_fields(serializer, company):
    """Restrict every writable related field on ``serializer`` to ``company``.

    Walks into ``many=True`` wrappers and nested serializers. A field whose
    model has no route to a company (Skill on a shared table, say) is left
    alone, so this cannot accidentally hide global reference data.
    """
    fields = getattr(serializer, "fields", None)
    if not fields:
        return
    for field in fields.values():
        child = getattr(field, "child_relation", None) or field
        if isinstance(child, drf_serializers.BaseSerializer):
            scope_related_fields(child, company)
            continue
        queryset = getattr(child, "queryset", None)
        if queryset is None or child.read_only:
            continue
        path = _company_path(queryset.model)
        if path is None:
            continue
        child.queryset = queryset.none() if company is None else queryset.filter(**{path: company})


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
            company = Company.objects.filter(slug=slug, memberships__user=user).first()
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

    def get_serializer(self, *args, **kwargs):
        """Scope writable relations, not just the queryset we read from.

        ``get_queryset`` only filtered what a client can READ. Every writable
        ``PrimaryKeyRelatedField`` still accepted any primary key in the table,
        so a recruiter could POST another tenant's question ids onto their own
        assessment and get them back serialised - answer keys included. Rather
        than remembering to scope each field by hand, rebind every related
        field whose model is company-owned to this request's company.
        """
        serializer = super().get_serializer(*args, **kwargs)
        scope_related_fields(serializer, self.company)
        return serializer
