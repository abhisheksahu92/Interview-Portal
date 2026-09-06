"""Constants behind the public policy pages.

Razorpay will not activate a live merchant account without published terms,
privacy, refund and contact pages, so these live in the app rather than in a
CMS: they must ship with the code and be diffable in review.

One version stamp serves both the pages and ``core.models.User`` — signup
records the ``POLICY_VERSION`` the user actually agreed to, so a later change
to these documents is visible as "who accepted what".

Bump ``POLICY_VERSION`` **and** ``POLICY_UPDATED`` together whenever the
substance of a policy changes.
"""

from datetime import date

#: Stored on ``User.policy_version`` at signup (CharField(max_length=20)).
POLICY_VERSION = "1.0"

#: Rendered as "Last updated" on every policy page.
POLICY_UPDATED = date(2026, 9, 7)

#: Trading name shown on the policy and contact pages.
BUSINESS_NAME = "Interview Portal"

# Owner-facing contact points. These must resolve to a mailbox someone reads:
# Razorpay's activation review sends a test mail to the address published here.
CONTACT_EMAIL = "support@interviewportal.in"
GRIEVANCE_EMAIL = "grievance@interviewportal.in"

# ---------------------------------------------------------------------------
# LEGALLY REQUIRED, DELIBERATELY BLANK.
# Razorpay's merchant policy requires a registered business name, address and
# phone number on the contact page, and the DPDP Act requires a *named*
# Grievance Officer. Nobody but the account owner knows these, so they are
# empty strings here and the contact page renders a loud "not filled in" box
# instead of inventing one. Fill them in before going live.
# ---------------------------------------------------------------------------
LEGAL_ENTITY_NAME = ""
REGISTERED_ADDRESS = ""
CONTACT_PHONE = ""
GSTIN = ""
GRIEVANCE_OFFICER = ""

#: Where disputes are heard. Also owner-supplied.
JURISDICTION_CITY = ""


def policy_context():
    """Template context shared by all four public policy pages."""
    return {
        "policy_version": POLICY_VERSION,
        "policy_updated": POLICY_UPDATED,
        "business_name": BUSINESS_NAME,
        "contact_email": CONTACT_EMAIL,
        "grievance_email": GRIEVANCE_EMAIL,
        "legal_entity_name": LEGAL_ENTITY_NAME,
        "registered_address": REGISTERED_ADDRESS,
        "contact_phone": CONTACT_PHONE,
        "gstin": GSTIN,
        "grievance_officer": GRIEVANCE_OFFICER,
        "jurisdiction_city": JURISDICTION_CITY,
    }
