"""Meta error codes, classified. Built from Meta's WhatsApp Cloud API error reference
(developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes) for
the calls we make: code exchange, subscribed_apps, register, messages (send, templates, mark
read) and the phone number / business reads.

The kind decides what the platform does (an auth error stops sending until the customer
reconnects); the internal code is stable and is what products translate for people.
"""

from dataclasses import dataclass
from enum import StrEnum


class MetaErrorKind(StrEnum):
    AUTH = "auth"  # the token or a permission is gone: sending stops until reconnected
    ACCOUNT = "account"  # the WhatsApp account or number has a problem on Meta's side
    THROTTLE = "throttle"  # slow down and retry
    RECIPIENT = "recipient"  # this one message cannot reach this person
    TEMPLATE = "template"
    REGISTRATION = "registration"  # registering the number (Embedded Signup)
    REQUEST = "request"  # our request was wrong; a bug on our side
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MetaError:
    meta_code: str
    code: str  # stable internal code
    kind: MetaErrorKind


_TABLE: dict[str, tuple[str, MetaErrorKind]] = {
    # Authorization
    "0": ("token_revoked", MetaErrorKind.AUTH),
    "190": ("token_revoked", MetaErrorKind.AUTH),
    "3": ("permission_missing", MetaErrorKind.AUTH),
    "10": ("permission_missing", MetaErrorKind.AUTH),
    "200": ("permission_missing", MetaErrorKind.AUTH),
    "131005": ("permission_missing", MetaErrorKind.AUTH),
    # Throttling
    "4": ("rate_limited", MetaErrorKind.THROTTLE),
    "80007": ("rate_limited", MetaErrorKind.THROTTLE),
    "130429": ("rate_limited", MetaErrorKind.THROTTLE),
    "131056": ("rate_limited", MetaErrorKind.THROTTLE),
    "131048": ("sending_restricted", MetaErrorKind.ACCOUNT),
    # Integrity and account
    "368": ("account_restricted", MetaErrorKind.ACCOUNT),
    "131031": ("account_restricted", MetaErrorKind.ACCOUNT),
    "130497": ("country_restricted", MetaErrorKind.ACCOUNT),
    "131042": ("payment_method", MetaErrorKind.ACCOUNT),
    "131037": ("display_name_missing", MetaErrorKind.ACCOUNT),
    "2494100": ("number_maintenance", MetaErrorKind.ACCOUNT),
    # One message, one recipient
    "131026": ("recipient_unavailable", MetaErrorKind.RECIPIENT),
    "131021": ("recipient_is_sender", MetaErrorKind.RECIPIENT),
    "131047": ("outside_service_window", MetaErrorKind.RECIPIENT),
    "131051": ("unsupported_message", MetaErrorKind.RECIPIENT),
    # Templates
    "132000": ("template_parameters", MetaErrorKind.TEMPLATE),
    "132012": ("template_parameters", MetaErrorKind.TEMPLATE),
    "132001": ("template_not_found", MetaErrorKind.TEMPLATE),
    "132005": ("template_too_long", MetaErrorKind.TEMPLATE),
    "132007": ("template_policy", MetaErrorKind.TEMPLATE),
    "132015": ("template_paused", MetaErrorKind.TEMPLATE),
    "132016": ("template_paused", MetaErrorKind.TEMPLATE),
    # Registering the number
    "131045": ("number_not_registered", MetaErrorKind.REGISTRATION),
    "133010": ("number_not_registered", MetaErrorKind.REGISTRATION),
    "133000": ("previous_deregistration_failed", MetaErrorKind.REGISTRATION),
    "133005": ("pin_mismatch", MetaErrorKind.REGISTRATION),
    "133008": ("pin_mismatch", MetaErrorKind.REGISTRATION),
    "133009": ("pin_mismatch", MetaErrorKind.REGISTRATION),
    "133006": ("number_not_verified", MetaErrorKind.REGISTRATION),
    "133015": ("registration_limit", MetaErrorKind.REGISTRATION),
    "133016": ("registration_limit", MetaErrorKind.REGISTRATION),
    "2388012": ("number_in_other_account", MetaErrorKind.REGISTRATION),
    # Our own requests
    "100": ("bad_request", MetaErrorKind.REQUEST),
    "131008": ("bad_request", MetaErrorKind.REQUEST),
    "131009": ("bad_request", MetaErrorKind.REQUEST),
    "135000": ("bad_request", MetaErrorKind.REQUEST),
    # Temporary on Meta's side (retried)
    "131016": ("meta_unavailable", MetaErrorKind.THROTTLE),
    "133004": ("meta_unavailable", MetaErrorKind.THROTTLE),
    "131000": ("meta_unknown", MetaErrorKind.UNKNOWN),
}

# Codes our own platform uses for Meta-related states (webhook events, the network).
INTERNAL: dict[str, MetaErrorKind] = {
    "app_removed": MetaErrorKind.AUTH,
    "account_disabled": MetaErrorKind.ACCOUNT,
    "account_restricted": MetaErrorKind.ACCOUNT,
    "account_deleted": MetaErrorKind.ACCOUNT,
    "number_offboarded": MetaErrorKind.ACCOUNT,
    "network_error": MetaErrorKind.THROTTLE,
}


def classify(meta_code: str | None) -> MetaError:
    """Unknown codes are UNKNOWN (never AUTH: sending is only stopped for codes we know)."""
    raw = (meta_code or "").strip()
    if raw in _TABLE:
        code, kind = _TABLE[raw]
        return MetaError(raw, code, kind)
    if raw in INTERNAL:
        return MetaError(raw, raw, INTERNAL[raw])
    # 200-299: "permission not granted or removed".
    if raw.isdigit() and 200 <= int(raw) <= 299:
        return MetaError(raw, "permission_missing", MetaErrorKind.AUTH)
    return MetaError(raw, "unknown", MetaErrorKind.UNKNOWN)


def mapped_codes() -> tuple[str, ...]:
    """Every Meta code with its own entry (the tests cover each one)."""
    return tuple(_TABLE)
