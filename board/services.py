"""Query helpers for the cross-tenant job board.

These are the public API other apps (the seeker feed) consume, so the
"is this job listable?" rule lives here once: OPEN jobs whose company runs a
published careers site that opted into the network.
"""

from django.db.models import Q

from jobs.models import Job

#: Locations that mean "no office" when a job carries no explicit remote flag.
REMOTE_WORDS = ("remote", "anywhere", "work from home", "wfh")


def _base():
    return (
        Job.objects.filter(
            status=Job.OPEN,
            company__careers_site__published=True,
            company__careers_site__list_in_network=True,
        )
        .select_related("company", "company__careers_site")
        .prefetch_related("skills")
    )


def is_remote(job):
    """True when the posting reads as remote — location text is all we have."""
    location = (job.location or "").strip().lower()
    if not location:
        return True
    return any(word in location for word in REMOTE_WORDS)


def network_jobs(query="", skills=None, remote=None):
    """Listable jobs, newest first, narrowed by free text / skills / remote.

    ``remote`` is applied in SQL as a location text match so the caller still
    gets a queryset (paginated by the list view) rather than a list.
    """
    jobs = _base()
    query = (query or "").strip()
    if query:
        jobs = jobs.filter(
            Q(title__icontains=query)
            | Q(skills__name__icontains=query)
            | Q(location__icontains=query)
        )
    if skills:
        names = [s for s in (str(s).strip() for s in skills) if s]
        if names:
            match = Q()
            for name in names:
                match |= Q(skills__name__iexact=name)
            jobs = jobs.filter(match)
    if remote is not None:
        match = Q(location="")
        for word in REMOTE_WORDS:
            match |= Q(location__icontains=word)
        jobs = jobs.filter(match) if remote else jobs.exclude(match)
    return jobs.distinct().order_by("-created_at", "-pk")


def _names(skills):
    return {(getattr(s, "name", s) or "").strip().casefold() for s in skills} - {""}


def match_score(job_skill_names, wanted):
    """Jaccard overlap of two skill-name sets, 0..1."""
    if not job_skill_names or not wanted:
        return 0.0
    union = job_skill_names | wanted
    return len(job_skill_names & wanted) / len(union)


def network_jobs_for(candidate_profile, limit=50):
    """Listable jobs ranked by skill overlap with the candidate, then recency.

    Each row carries ``match`` (0..100) so feed cards can show a match badge.
    Ranking is done in Python: the sets are small and Jaccard has no SQL form.
    """
    wanted = _names(candidate_profile.skills.all()) if candidate_profile else set()
    jobs = list(network_jobs()[: max(limit * 5, limit)])
    for job in jobs:
        job.match = round(match_score(_names(job.skills.all()), wanted) * 100)
    jobs.sort(key=lambda j: (-j.match, -j.created_at.timestamp(), -j.pk))
    return jobs[:limit]
