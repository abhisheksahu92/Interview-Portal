"""Public careers pages, feeds, and the recruiter-facing site editor."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing.entitlements import require_feature
from careers import gateway
from careers.feeds import indeed_feed_xml
from careers.forms import CareersSiteForm
from careers.models import CareersSite, JobDistribution
from careers.seo import job_posting_json
from careers.text import render_about
from jobs.models import Job

BOARD_ORDER = [
    JobDistribution.INDEED,
    JobDistribution.GOOGLE_JOBS,
    JobDistribution.LINKEDIN,
    JobDistribution.NAUKRI,
]


# --------------------------------------------------------------------------- public


def _site_or_404(slug):
    site = CareersSite.objects.filter(slug=slug).select_related("company").first()
    if site is None or not site.published:
        raise Http404("No careers site here.")
    return site


def _filtered_jobs(site, request):
    jobs = site.open_jobs()
    location = (request.GET.get("location") or "").strip()
    query = (request.GET.get("q") or "").strip()
    if location:
        jobs = jobs.filter(location__icontains=location)
    if query:
        jobs = jobs.filter(
            Q(title__icontains=query) | Q(skills__name__icontains=query)
        ).distinct()
    return jobs, {"location": location, "q": query}


def _public_context(site, request, jobs=None, filters=None):
    locations = sorted(
        {j.location for j in site.open_jobs() if j.location}
    )
    return {
        "site": site,
        "company": site.company,
        "jobs": jobs if jobs is not None else site.open_jobs(),
        "filters": filters or {"location": "", "q": ""},
        "locations": locations,
        "about_html": render_about(site.about),
        "canonical": gateway.absolute(reverse("careers:site", args=[site.slug])),
    }


def public_site(request, slug):
    """Branded public careers page: hero + searchable job list."""
    site = _site_or_404(slug)
    jobs, filters = _filtered_jobs(site, request)
    return render(request, "careers/public_site.html", _public_context(site, request, jobs, filters))


def public_job(request, slug, pk):
    """Public job detail with JobPosting JSON-LD and Open Graph tags."""
    site = _site_or_404(slug)
    job = get_object_or_404(
        Job.objects.select_related("company").prefetch_related("skills"),
        pk=pk,
        company=site.company,
        status=Job.OPEN,
    )
    context = _public_context(site, request)
    context.update(
        job=job,
        job_ld=job_posting_json(job, site),
        description_html=render_about(job.description),
        requirements_html=render_about(job.requirements),
        canonical=gateway.absolute(reverse("careers:job_detail", args=[site.slug, job.pk])),
    )
    return render(request, "careers/public_job.html", context)


def sitemap(request, slug):
    """Per-site sitemap.xml listing the careers page and every OPEN job."""
    site = _site_or_404(slug)
    urls = [(gateway.absolute(reverse("careers:site", args=[site.slug])), None)]
    for job in site.open_jobs():
        urls.append(
            (
                gateway.absolute(reverse("careers:job_detail", args=[site.slug, job.pk])),
                job.created_at.date().isoformat(),
            )
        )
    return render(
        request,
        "careers/sitemap.xml",
        {"urls": urls},
        content_type="application/xml",
    )


def indeed_feed(request):
    """Indeed XML feed across every published site's OPEN jobs."""
    return HttpResponse(indeed_feed_xml(), content_type="application/xml")


# --------------------------------------------------------------------------- recruiter


def _site_for(company):
    site = CareersSite.objects.filter(company=company).first()
    if site is None:
        site = CareersSite.objects.create(company=company, published=False)
    return site


def index(request):
    """Careers settings for the active company.

    Doubles as the custom-domain entry point: when the request's Host header
    matches a published site's ``custom_domain`` the public site is served here
    instead (the host must also be listed in ``ALLOWED_HOSTS``).
    """
    site = CareersSite.for_host(request.get_host())
    if site is not None:
        jobs, filters = _filtered_jobs(site, request)
        return render(
            request, "careers/public_site.html", _public_context(site, request, jobs, filters)
        )
    return settings_view(request)


@login_required
@require_feature("careers_page")
def settings_view(request):
    company = getattr(request, "company", None)
    if company is None:
        raise Http404("No active company.")
    site = _site_for(company)
    form = CareersSiteForm(instance=site)
    if request.method == "POST":
        if "publish" in request.POST:
            site.published = not site.published
            site.save(update_fields=["published", "updated_at"])
            messages.success(
                request, "Careers site published." if site.published else "Careers site unpublished."
            )
            return redirect("careers:index")
        form = CareersSiteForm(request.POST, request.FILES, instance=site)
        if form.is_valid():
            form.save()
            messages.success(request, "Careers site saved.")
            return redirect("careers:index")
        messages.error(request, "Please fix the errors below.")
    return render(
        request,
        "careers/settings.html",
        {
            "site": site,
            "form": form,
            "preview_url": reverse("careers:preview"),
            "public_url": gateway.absolute(reverse("careers:site", args=[site.slug])),
            "indeed_feed_url": gateway.absolute(reverse("careers:indeed_feed")),
            "jobs": Job.objects.filter(company=company).order_by("-created_at")[:50],
            "adapters": [gateway.adapter_for(b) for b in BOARD_ORDER],
        },
    )


@login_required
@require_feature("careers_page")
def preview(request):
    """Unpublished live preview of the active company's site, for the editor iframe."""
    company = getattr(request, "company", None)
    if company is None:
        raise Http404("No active company.")
    site = _site_for(company)
    context = _public_context(site, request)
    context["is_preview"] = True
    return render(request, "careers/public_site.html", context)


def _distribution_rows(job):
    existing = {d.board: d for d in job.distributions.all()}
    rows = []
    for board in BOARD_ORDER:
        adapter = gateway.adapter_for(board)
        rows.append(
            {
                "board": board,
                "label": adapter.label,
                "kind": adapter.kind,
                "connection": adapter.status(),
                "distribution": existing.get(board),
            }
        )
    return rows


@login_required
@require_feature("careers_page")
def job_distribution(request, pk):
    """The per-job distribution panel (HTMX partial and full-page fallback)."""
    company = getattr(request, "company", None)
    job = get_object_or_404(Job, pk=pk, company=company)
    site = _site_for(company)
    return render(
        request,
        "careers/partials/job_distribution.html",
        {
            "job": job,
            "site": site,
            "rows": _distribution_rows(job),
            "posting_text": gateway.posting_text(job, site),
            "indeed_feed_url": gateway.absolute(reverse("careers:indeed_feed")),
        },
    )


@require_POST
@login_required
@require_feature("careers_page")
def distribute_action(request, pk, board):
    """Post or remove a job on one board, then re-render the panel."""
    company = getattr(request, "company", None)
    job = get_object_or_404(Job, pk=pk, company=company)
    adapter = gateway.adapter_for(board)
    if adapter is None:
        raise Http404("Unknown board.")
    action = request.POST.get("action", "post")
    distribution, _ = JobDistribution.objects.get_or_create(job=job, board=board)
    if adapter.kind != "push":
        distribution.status = JobDistribution.POSTED
        distribution.posted_at = timezone.now()
        distribution.last_error = ""
    else:
        result = adapter.remove(job) if action == "remove" else adapter.push(job)
        distribution.status = result["status"]
        distribution.external_id = result.get("external_id", "")
        distribution.last_error = result.get("error", "")
        distribution.posted_at = timezone.now() if result["ok"] and action != "remove" else None
    distribution.save()
    return job_distribution(request, pk=job.pk)
