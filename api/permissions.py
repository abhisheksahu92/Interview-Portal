"""DRF permissions for the tenant-scoped API."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.models import Membership

RECRUITER_ROLES = (Membership.OWNER, Membership.RECRUITER)


def _company(request, view):
    company = getattr(view, "company", None)
    if company is None:
        company = getattr(request, "company", None)
    return company


def _role(request, view):
    user = request.user
    if not user or not user.is_authenticated:
        return None
    return user.role_in(_company(request, view))


class IsCompanyMember(BasePermission):
    """Authenticated user with a membership in the resolved company."""

    message = "You are not a member of this company."

    def has_permission(self, request, view):
        return _role(request, view) is not None


class IsRecruiterOrOwner(IsCompanyMember):
    """Write access limited to OWNER/RECRUITER; reads open to any member."""

    message = "Recruiter or owner role required."

    def has_permission(self, request, view):
        role = _role(request, view)
        if role is None:
            return False
        if request.method in SAFE_METHODS:
            return True
        return role in RECRUITER_ROLES


class IsInterviewer(IsCompanyMember):
    """Any member may review; interviewers are the primary audience."""

    message = "Interviewer, recruiter or owner role required."

    def has_permission(self, request, view):
        role = _role(request, view)
        return role in (
            Membership.OWNER,
            Membership.RECRUITER,
            Membership.INTERVIEWER,
        )


class IsCandidateOwner(BasePermission):
    """Object-level: the candidate profile (or its owner) must be request.user."""

    message = "You do not own this candidate record."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        owner = getattr(obj, "user", None)
        if owner is None:
            candidate = getattr(obj, "candidate", None)
            owner = getattr(candidate, "user", None)
        return owner is not None and owner == user
