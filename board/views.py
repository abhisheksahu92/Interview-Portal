"""Public cross-tenant job board: list, detail, apply, sitemap."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from board.seo import board_job_posting_json
from board.services import is_remote, network_jobs
from careers import gateway
from careers.models import CareersSite
from careers.text import render_about
from core.models import Membership
from core.permissions import role_required
from web.services.apply import apply_to_job

PER_PAGE = 20

SEO_DESCRIPTION = (
    "Open roles from every company hiring on the network — search by title, "
    "skill or location and apply in one click."
)


def _filters(request):
    remote = request.GET.get("remote")
    return {
        "q": (request.GET.get("q") or "").strip(),
        "remote": True if remote in ("1", "on", "true") else None,
    }


def job_list(request):
    """Searchable, paginated list of every job the network may show."""
    filters = _filters(request)
    jobs = network_jobs(query=filters["q"], remote=filters["remote"])
    page = Paginator(jobs, PER_PAGE).get_page(request.GET.get("page"))
    return render(
        request,
        "board/job_list.html",
        {
            "page_obj": page,
            "jobs": page.object_list,
            "filters": filters,
            "total": page.paginator.count,
            "canonical": gateway.absolute(reverse("board:list")),
            "seo_description": SEO_DESCRIPTION,
        },
    )


def _listed_job(pk):
    """A job that is currently listable on the network, or 404.

    Going through ``network_jobs`` keeps one definition of "listed": a job whose
    site unpublishes or opts out disappears from the detail page too.
    """
    return get_object_or_404(network_jobs(), pk=pk)


def job_detail(request, pk):
    """Job detail with JobPosting JSON-LD and the apply call to action."""
    job = _listed_job(pk)
    site = job.company.careers_site
    already_applied = bool(
        request.user.is_authenticated
        and job.applications.filter(candidate__user=request.user).exists()
    )
    return render(
        request,
        "board/job_detail.html",
        {
            "job": job,
            "site": site,
            "company": job.company,
            "job_ld": board_job_posting_json(job, site),
            "description_html": render_about(job.description),
            "requirements_html": render_about(job.requirements),
            "is_remote": is_remote(job),
            "already_applied": already_applied,
            "canonical": gateway.absolute(reverse("board:job_detail", args=[job.pk])),
            "seo_description": (
                f"{job.title} at {job.company.name}"
                + (f" — {job.location}" if job.location else " — remote")
            ),
        },
    )


@require_POST
def job_apply(request, pk):
    """Apply as a candidate; send everyone else somewhere they can become one."""
    job = _listed_job(pk)
    detail = reverse("board:job_detail", args=[job.pk])
    if not request.user.is_authenticated:
        return redirect(f"{reverse('core:candidate_signup')}?next={detail}")
    if not request.user.is_candidate:
        messages.error(request, "Company members apply from their own account.")
        return redirect(detail)
    application = apply_to_job(request.user, job)
    if application.was_created:
        messages.success(request, f"Applied to {job.title}.")
    else:
        messages.info(request, "You have already applied to this job.")
    return redirect("web:candidate_home")


def sitemap(request):
    """sitemap.xml for the board list plus every listed job."""
    urls = [(gateway.absolute(reverse("board:list")), None)]
    for job in network_jobs():
        urls.append(
            (
                gateway.absolute(reverse("board:job_detail", args=[job.pk])),
                job.created_at.date().isoformat(),
            )
        )
    return render(request, "careers/sitemap.xml", {"urls": urls}, content_type="application/xml")


@login_required
@role_required(Membership.OWNER, Membership.RECRUITER)
@require_POST
def network_toggle(request):
    """Opt the active company's careers site in or out of the network.

    Lives here rather than in careers/views.py so the board owns its own switch.
    """
    company = getattr(request, "company", None)
    if company is None:
        raise Http404("No active company.")
    site = CareersSite.objects.filter(company=company).first()
    if site is None:
        site = CareersSite.objects.create(company=company, published=False)
    site.list_in_network = not site.list_in_network
    site.save(update_fields=["list_in_network", "updated_at"])
    messages.success(
        request,
        "Listing on the job network." if site.list_in_network else "Removed from the job network.",
    )
    return redirect("careers:index")
