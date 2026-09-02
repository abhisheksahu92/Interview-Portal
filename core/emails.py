"""Outgoing transactional email for core (currently: team invitations)."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_invitation(invitation, request=None):
    """Email the invite link to ``invitation.email``. Returns the send count."""
    context = {
        "invitation": invitation,
        "company": invitation.company,
        "role": invitation.get_role_display(),
        "invited_by": invitation.invited_by,
        "accept_url": invitation.accept_url(request),
        "expires_at": invitation.expires_at,
    }
    subject = f"You are invited to join {invitation.company.name} on Interview Portal"
    text_body = render_to_string("core/email/invitation.txt", context)
    html_body = render_to_string("core/email/invitation.html", context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[invitation.email],
    )
    message.attach_alternative(html_body, "text/html")
    return message.send()
