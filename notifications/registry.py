"""Event registry for the notifications app.

Every notification other apps can send is registered here with the template
prefix used to render it and the channels that make sense for it. Templates
live at ``notifications/templates/notifications/<event>.{subject.txt,txt,html,whatsapp.txt}``.
"""

from dataclasses import dataclass, field

EMAIL = "email"
WHATSAPP = "whatsapp"
SMS = "sms"

CHANNELS = (EMAIL, WHATSAPP, SMS)

#: Pseudo-channel: opting out of it stops the non-essential *email* events
#: only. Transactional mail a candidate needs (below) is still delivered.
MARKETING_EMAIL = "email_marketing"

#: Channels a candidate may opt out of (a superset of the sending channels).
OPT_OUT_CHANNELS = CHANNELS + (MARKETING_EMAIL,)

CHANNEL_LABELS = {
    EMAIL: "Email",
    WHATSAPP: "WhatsApp",
    SMS: "SMS",
    MARKETING_EMAIL: "Non-essential email",
}

#: Events that are always delivered by email, whatever the opt-out state.
ESSENTIAL_EVENTS = frozenset(
    {
        "application_received",
        "assessment_result",
        "offer_sent",
        "interview_scheduled",
        "interview_reminder",
        "interview_cancelled",
        "invitation",
        "payment_failed",
        "usage_warning",
    }
)


def is_essential(event_name) -> bool:
    """True when ``event_name`` must be sent even to an opted-out candidate."""
    return event_name in ESSENTIAL_EVENTS


@dataclass(frozen=True)
class Event:
    """One registered notification event."""

    name: str
    label: str
    description: str = ""
    template: str = ""
    channels: tuple = field(default=(EMAIL, WHATSAPP))
    whatsapp_template_name: str = ""

    @property
    def template_prefix(self) -> str:
        return self.template or self.name


_EVENTS: "dict[str, Event]" = {}


def register(event: Event) -> Event:
    """Add (or replace) an event in the registry."""
    _EVENTS[event.name] = event
    return event


def all_events() -> "list[Event]":
    """Registered events in registration order."""
    return list(_EVENTS.values())


def event_names() -> "list[str]":
    return list(_EVENTS)


def get_event(name: str) -> Event:
    """Look up an event, raising ``UnknownEvent`` when it is not registered."""
    try:
        return _EVENTS[name]
    except KeyError:
        raise UnknownEvent(name) from None


class UnknownEvent(KeyError):
    """Raised when an unregistered event name is sent."""

    def __init__(self, name):
        self.event = name
        super().__init__(f"Unknown notification event {name!r}")


for _event in (
    Event("application_received", "Application received", "Sent to a candidate when they apply."),
    Event("stage_advanced", "Stage advanced", "Sent when an application moves to the next stage."),
    Event("application_rejected", "Application rejected", "Sent when an application is rejected."),
    Event("application_hired", "Candidate hired", "Sent when an application reaches HIRED."),
    Event("interview_scheduled", "Interview scheduled", "Sent when an interview is booked."),
    Event("interview_reminder", "Interview reminder", "Reminder before an interview starts."),
    Event("assessment_result", "Assessment result", "Sent when an assessment is graded."),
    Event("offer_sent", "Offer sent", "Sent when an offer letter goes out."),
    Event("submission_feedback", "Submission feedback", "Client feedback on a submitted candidate."),
    Event("offer_accepted", "Offer accepted", "Sent to the recruiter when a candidate accepts an offer.", channels=(EMAIL,)),
    Event("offer_declined", "Offer declined", "Sent to the recruiter when a candidate declines an offer.", channels=(EMAIL,)),
    Event("interview_cancelled", "Interview cancelled", "Sent when a booked interview is cancelled."),
    Event("video_invite", "Video screen invite", "Asks a candidate to record their video answers."),
    Event("client_access_invite", "Client portal invite", "Sends a client contact their portal link.", channels=(EMAIL,)),
    Event("client_new_submission", "New client submission", "Tells a client a new candidate is waiting for review.", channels=(EMAIL,)),
    Event("talent_pool_invite", "Talent pool invite", "Invites a pooled candidate to apply for a role."),
    Event("usage_warning", "Usage warning", "Plan quota nearly exhausted.", channels=(EMAIL,)),
    Event("payment_failed", "Payment failed", "A subscription payment could not be taken.", channels=(EMAIL,)),
    Event("invitation", "Team invitation", "Invite a teammate to the company.", channels=(EMAIL,)),
    # --- contracting (staffing back office) ---
    Event("timesheet_submitted", "Timesheet submitted", "A contractor submitted a timesheet for approval."),
    Event("timesheet_approved", "Timesheet approved", "Tells a contractor their timesheet was approved."),
    Event("timesheet_rejected", "Timesheet rejected", "Tells a contractor their timesheet was sent back."),
    Event("client_invoice_sent", "Client invoice sent", "Emails a client their GST invoice.", channels=(EMAIL,)),
    # --- exchange (agency requirement network) ---
    Event("exchange_partner_invite", "Exchange partner invite", "An agency wants to partner on the exchange.", channels=(EMAIL,)),
    Event("exchange_partner_accepted", "Exchange partner accepted", "A partner accepted your exchange invite.", channels=(EMAIL,)),
    Event("exchange_submission_received", "Exchange submission received", "A partner submitted a candidate for your requirement.", channels=(EMAIL,)),
    Event("exchange_submission_shortlisted", "Exchange submission shortlisted", "Your submitted candidate was shortlisted.", channels=(EMAIL,)),
    Event("exchange_submission_rejected", "Exchange submission rejected", "Your submitted candidate was passed on.", channels=(EMAIL,)),
    Event("exchange_submission_revealed", "Exchange candidate revealed", "The requester revealed your candidate's details.", channels=(EMAIL,)),
    Event("exchange_submission_hired", "Exchange placement made", "Your submitted candidate was hired.", channels=(EMAIL,)),
    Event("exchange_deal_disputed", "Exchange deal disputed", "The other side raised a dispute on a deal.", channels=(EMAIL,)),
):
    register(_event)

del _event
