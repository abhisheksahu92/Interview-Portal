"""``{% load contracting_portal %}`` — data for the client-portal timesheet panel.

The clients app includes ``contracting/partials/portal_timesheets.html`` with
nothing but ``access``, so the partial fetches its own rows through this tag.
That keeps the one sanctioned edit to ``clients/`` to a single include line and
means the same partial serves both the full portal page and the HTMX response
after an approve/reject.
"""

from django import template

register = template.Library()


@register.simple_tag
def portal_timesheets(access):
    """Pending and recent timesheets visible to one client access link."""
    from contracting.views import portal_timesheets_context

    if access is None or getattr(access, "client_id", None) is None:
        return {"access": access, "pending": [], "recent": []}
    return portal_timesheets_context(access)
