"""Event payload builders — the public shape of our webhook ``data`` object.

These are deliberately hand-written rather than derived from DRF serializers:
a webhook body is a published contract, and it must not change shape because
somebody added a field to an internal serializer.
"""


def _iso(value):
    return value.isoformat() if value is not None else None


def candidate_data(candidate):
    if candidate is None:
        return {}
    user = getattr(candidate, "user", None)
    return {
        "id": candidate.pk,
        "email": getattr(user, "email", None),
        "name": (getattr(user, "get_full_name", lambda: "")() or None),
        "phone": candidate.phone or None,
        "experience_years": str(candidate.experience_years),
    }


def application_data(application):
    job = application.job
    stage = application.current_stage
    return {
        "id": application.pk,
        "status": application.status,
        "created_at": _iso(application.created_at),
        "job": {
            "id": job.pk,
            "title": job.title,
            "location": job.location,
            "status": job.status,
        },
        "stage": ({"id": stage.pk, "name": stage.name, "kind": stage.kind} if stage else None),
        "candidate": candidate_data(application.candidate),
        "ai_fit_score": application.ai_fit_score,
    }


def offer_data(offer):
    return {
        "id": offer.pk,
        "status": offer.status,
        "salary": str(offer.salary),
        "currency": offer.currency,
        "joining_date": _iso(offer.joining_date),
        "signed_name": offer.signed_name or None,
        "signed_at": _iso(offer.signed_at),
        "application": application_data(offer.application),
    }


def interview_data(interview):
    return {
        "id": interview.pk,
        "status": interview.status,
        "scheduled_start": _iso(interview.scheduled_start),
        "scheduled_end": _iso(interview.scheduled_end),
        "timezone": interview.timezone,
        "location_or_link": interview.location_or_link,
        "interviewers": [u.email for u in interview.interviewers.all()],
        "application": application_data(interview.application),
    }


def attempt_data(attempt):
    assessment = attempt.assessment
    return {
        "id": attempt.pk,
        "assessment": {
            "id": getattr(assessment, "pk", None),
            "title": getattr(assessment, "title", None),
        },
        "score_percent": (
            str(attempt.score_percent) if attempt.score_percent is not None else None
        ),
        "passed": attempt.passed,
        "submitted_at": _iso(attempt.submitted_at),
        "application": application_data(attempt.application),
    }
