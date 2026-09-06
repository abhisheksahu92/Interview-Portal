"""Applying to a job, shared by the public job page, the board and the seeker portal.

Extracted from ``web.views.job_apply`` so every entry point creates applications
the same way — one row per (job, candidate), never a duplicate on a second click.
"""

from jobs.models import Application, CandidateProfile


def apply_to_job(user, job):
    """Apply ``user`` to ``job`` and return the Application.

    Idempotent: a repeat call returns the existing row. The returned object
    carries ``was_created`` so callers can word their own message.
    """
    profile, _ = CandidateProfile.objects.get_or_create(user=user)
    application, created = Application.objects.get_or_create(
        job=job,
        candidate=profile,
        defaults={"current_stage": job.first_stage},
    )
    application.was_created = created
    return application
