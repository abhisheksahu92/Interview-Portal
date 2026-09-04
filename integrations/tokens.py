"""Per-company API tokens.

``rest_framework.authtoken`` stores at most one token per *user*, but an API
key must belong to the company rather than to whichever employee happened to
create it — otherwise deactivating a leaver silently breaks the customer's
integration.

So each company gets a dedicated service user ``api@<slug>.local`` holding a
RECRUITER membership (read everything, write the recruiter-level endpoints, no
owner-only actions such as billing), and that user's authtoken *is* the
company's API key. Minting rotates the token; revoking deletes it. The service
user is created with an unusable password, so the key is the only way in and it
can never be used to sign into the web UI.

Individual humans can still mint a personal token with
``POST /api/v1/auth/token/``; those are scoped by their own memberships and are
unaffected by rotation here.
"""

from rest_framework.authtoken.models import Token

from core.models import Membership, User

EMAIL_TEMPLATE = "api@{slug}.local"


def service_email(company):
    return EMAIL_TEMPLATE.format(slug=company.slug)


def service_user(company, create=True):
    """The company's API service user, created on demand."""
    email = service_email(company)
    user = User.objects.filter(email=email).first()
    if user is None:
        if not create:
            return None
        user = User.objects.create_user(
            email=email, password=None, first_name="API", last_name="Service"
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
    Membership.objects.get_or_create(
        user=user, company=company, defaults={"role": Membership.RECRUITER}
    )
    return user


def get_token(company):
    """The company's current token, or None."""
    user = service_user(company, create=False)
    if user is None:
        return None
    return Token.objects.filter(user=user).first()


def issue_token(company):
    """Mint (or rotate) the company's API token and return it.

    The plaintext key is only visible in the response of this call — the UI
    shows it once and stores nothing extra.
    """
    user = service_user(company)
    Token.objects.filter(user=user).delete()
    return Token.objects.create(user=user)


def revoke_token(company):
    """Delete the company's token. Returns True when one existed."""
    token = get_token(company)
    if token is None:
        return False
    token.delete()
    return True


def masked(key):
    """``abcd1234…wxyz`` — enough to recognise a key, not enough to use it."""
    if not key:
        return ""
    if len(key) <= 12:
        return "•" * len(key)
    return f"{key[:6]}{'•' * 8}{key[-4:]}"
