"""Client-portal services: submissions, access links and portal notifications."""

import logging

from django.urls import reverse

from clients.models import Client, ClientAccess, Submission
from clients.notify import send_event

logger = logging.getLogger(__name__)

FEEDBACK_COOLDOWN_SECONDS = 3


class CrossCompanySubmission(ValueError):
    """Raised when an application and a client belong to different tenants."""


def submit_application(application, client, submitted_by=None, note="", notify=True):
    """Create the Submission linking ``application`` to ``client``.

    Refuses cross-tenant pairs outright: the client and the application's job must
    belong to the same company.
    """
    if application.job.company_id != client.company_id:
        raise CrossCompanySubmission(
            "Cannot submit an application to a client of another company."
        )
    submission, created = Submission.objects.get_or_create(
        application=application,
        client=client,
        defaults={"submitted_by": submitted_by, "note": note},
    )
    if created and notify:
        notify_client_of_submission(submission)
    return submission, created


def portal_url(access, request=None):
    path = reverse("clients:portal", args=[access.token])
    return request.build_absolute_uri(path) if request is not None else path


def issue_access(client, email, valid_days=None):
    """Create a fresh portal link for ``email`` on ``client``."""
    access = ClientAccess(client=client, email=email)
    access.expires_at = None
    access.save()
    return access.rotate(days=valid_days)


def send_access_link(access, request=None):
    """Email a portal link to the client contact."""
    url = portal_url(access, request)
    return send_event(
        "client_portal_invite",
        access.email,
        {
            "client": access.client.name,
            "company": access.client.company.name,
            "url": url,
            "expires_at": access.expires_at,
        },
        company=access.client.company,
        subject=f"Your candidate shortlist from {access.client.company.name}",
        body=(
            f"Hello,\n\nYou can review candidates submitted to {access.client.name} here:\n"
            f"{url}\n\nThis link expires on {access.expires_at:%d %b %Y}.\n"
        ),
    )


def notify_client_of_submission(submission):
    """Tell the client's active contacts that a new candidate is waiting."""
    accesses = [a for a in submission.client.accesses.all() if a.is_active]
    recipients = {a.email for a in accesses} or (
        {submission.client.contact_email} if submission.client.contact_email else set()
    )
    for email in recipients:
        send_event(
            "client_submission",
            email,
            {
                "client": submission.client.name,
                "job": submission.job.title,
                "candidate": submission.candidate.headline or str(submission.candidate),
            },
            company=submission.client.company,
            subject=f"New candidate for {submission.job.title}",
            body=(
                f"A new candidate has been submitted for {submission.job.title}.\n"
                "Sign in to your client portal link to review them.\n"
            ),
        )
    return len(recipients)


def notify_recruiter_of_feedback(submission, request=None):
    """Tell the submitting recruiter that the client has responded."""
    recipient = submission.submitted_by or submission.client.company.memberships.filter(
        role__in=["OWNER", "RECRUITER"]
    ).values_list("user__email", flat=True).first()
    if recipient is None:
        return False
    detail_path = reverse("clients:detail", args=[submission.client_id])
    url = request.build_absolute_uri(detail_path) if request is not None else detail_path
    return send_event(
        "submission_feedback",
        recipient,
        {
            "client": submission.client.name,
            "job": submission.job.title,
            "candidate": str(submission.candidate),
            "status": submission.get_status_display(),
            "feedback": submission.client_feedback,
            "rating": submission.client_rating,
            "url": url,
        },
        company=submission.client.company,
        subject=f"{submission.client.name}: {submission.get_status_display()} — {submission.job.title}",
        body=(
            f"{submission.client.name} marked {submission.candidate} as "
            f"{submission.get_status_display()} for {submission.job.title}.\n\n"
            f"Comment: {submission.client_feedback or '(none)'}\n"
            f"Rating: {submission.client_rating or '(none)'}\n\n{url}\n"
        ),
    )


def client_dashboard_context(client):
    """Jobs + submissions for one client, for the recruiter detail screen."""
    submissions = list(
        Submission.objects.filter(client=client)
        .select_related("application__job", "application__candidate__user", "submitted_by")
        .prefetch_related("application__attempts")
    )
    return {
        "client": client,
        "jobs": list(client.jobs.all()),
        "submissions": submissions,
        "accesses": list(client.accesses.all()),
    }


def grouped_submissions(client):
    """Portal view of a client's submissions, grouped by job."""
    submissions = (
        Submission.objects.filter(client=client)
        .select_related("application__job", "application__candidate__user")
        .prefetch_related("application__candidate__skills", "application__attempts")
        .order_by("application__job__title", "-created_at")
    )
    groups = {}
    for submission in submissions:
        groups.setdefault(submission.job, []).append(submission)
    return [{"job": job, "submissions": rows} for job, rows in groups.items()]


def best_attempt(application):
    """The highest-scoring graded assessment attempt, or None."""
    attempts = [a for a in application.attempts.all() if a.score_percent is not None]
    if not attempts:
        return None
    return max(attempts, key=lambda a: a.score_percent)


def clients_for(company):
    return Client.objects.for_company(company)
