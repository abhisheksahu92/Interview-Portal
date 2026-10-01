"""Tenant isolation foundation: querysets, models, and multi-hop resolution."""

from django.apps import apps
from django.db import models


TENANT_LOOKUP_MAP = {
    # Direct company foreign key
    "core.membership": "company",
    "core.invitation": "company",
    "jobs.skill": "company",
    "jobs.job": "company",
    "assessments.question": "company",
    "billing.subscription": "company",
    "billing.usagerecord": "company",
    "billing.invoice": "company",
    "billing.placementfee": "company",
    "billing.billingcharge": "company",
    "billing.pendingcheckout": "company",
    "scheduling.intervieweravailability": "company",
    "scheduling.interview": "company",
    "clients.client": "company",
    "notifications.notificationpreference": "company",
    "notifications.outboundmessage": "company",
    "talent.talentprofile": "company",
    "talent.importbatch": "company",
    "video.videoquestion": "company",
    "careers.careerssite": "company",
    "offers.offertemplate": "company",
    "partners.referral": "company",
    "partners.commissionledger": "company",
    "partners.whitelabel": "company",
    "partners.license": "company",
    "marketplace.packpurchase": "company",
    "integrations.outboundwebhook": "company",
    "integrations.connectorconfig": "company",
    "contracting.contractor": "company",
    "contracting.clientinvoicecounter": "company",
    "contracting.clientinvoice": "company",
    "contracting.payrollrun": "company",
    "exchange.exchangerequirement": "company",
    "bgv.verificationorder": "company",

    # Traversal via Job
    "jobs.pipelinestage": "job__company",
    "jobs.application": "job__company",
    "assessments.assessment": "job__company",
    "video.videoscreen": "job__company",
    "careers.jobdistribution": "job__company",

    # Traversal via Application
    "jobs.stagereview": "application__job__company",
    "assessments.attempt": "assessment__job__company",
    "clients.submission": "application__job__company",
    "video.videoinvite": "application__job__company",
    "video.videoresponse": "invite__application__job__company",
    "analytics.stagetransition": "application__job__company",
    "offers.offer": "application__job__company",
    "offers.offerevent": "offer__application__job__company",

    # Traversal via Client / Contractor
    "clients.clientaccess": "client__company",
    "contracting.clientbillingprofile": "client__company",
    "contracting.engagement": "contractor__company",
    "contracting.onboardingdocument": "contractor__company",
    "contracting.timesheet": "engagement__contractor__company",

    # Integrations, Scheduling, Video
    "integrations.webhookdelivery": "webhook__company",
    "integrations.connectorrun": "config__company",
    "scheduling.interviewslotproposal": "interview__company",
    "video.videoscreenquestion": "screen__job__company",
}


def get_company_lookup(model):
    """Return the ORM lookup string leading to Company, or None if global/unscoped."""
    if model is None:
        return None
    if isinstance(model, str):
        try:
            app_label, model_name = model.split(".", 1)
            model = apps.get_model(app_label, model_name)
        except Exception:
            return None

    model_key = f"{model._meta.app_label}.{model._meta.model_name}".lower()
    if model_key in TENANT_LOOKUP_MAP:
        return TENANT_LOOKUP_MAP[model_key]

    # Direct check on model fields
    try:
        f = model._meta.get_field("company")
        if f.is_relation and f.related_model._meta.model_name == "company":
            return "company"
    except Exception:
        pass

    # Direct FK named differently (e.g. from_company)
    for f in model._meta.fields:
        if f.is_relation and getattr(f.related_model, "_meta", None) and f.related_model._meta.model_name == "company":
            return f.name

    return None


def for_company(qs_or_model, company):
    """Scope a queryset or model manager to a company.

    Returns an empty queryset when ``company`` is None or model has no tenant mapping,
    preventing any accidental cross-tenant data leakage.
    """
    if hasattr(qs_or_model, "all"):
        qs = qs_or_model.all()
    else:
        qs = qs_or_model

    if company is None:
        return qs.none()

    lookup = get_company_lookup(qs.model)
    if lookup is None:
        # If model is directly Company itself
        if getattr(qs.model._meta, "model_name", "") == "company":
            return qs.filter(pk=getattr(company, "pk", company))
        return qs.none()

    return qs.filter(**{lookup: company})


class TenantQuerySet(models.QuerySet):
    """QuerySet that enforces tenant isolation.

    `for_company` returns an empty queryset when company is None to prevent
    accidental cross-tenant data leaks.
    """

    def for_company(self, company):
        return for_company(self, company)


class TenantModel(models.Model):
    """Abstract base model for all entities belonging to a specific tenant/company."""

    company = models.ForeignKey(
        "core.Company",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantQuerySet.as_manager()

    class Meta:
        abstract = True
