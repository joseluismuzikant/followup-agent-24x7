"""What happened with each reminder: one event per invoice and step (sent, failed, skipped
with a reason, escalated). They answer "was this step already done for this invoice?",
feed "Lo próximo", the backoffice's last errors and Day 11's dashboard. Reasons are codes,
never message text or phone numbers.

A send is the one WhatsApp message a client gets on a day (at most one per client per day,
enforced by the database): one or several invoices, one payment link."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class Outcome(StrEnum):
    SENT = "sent"
    FAILED = "failed"  # Meta refused this message for good (e.g. the number has no WhatsApp)
    SKIPPED = "skipped"  # not sent this time (reason); the step is still pending
    ESCALATED = "escalated"  # the owner was told; reminders stopped for the invoice


# A step counts as done for an invoice once it was sent, failed for good or escalated.
DONE = (Outcome.SENT, Outcome.FAILED, Outcome.ESCALATED)


class SkipReason(StrEnum):
    INVOICE_CLOSED = "invoice_closed"  # paid or cancelled before the send
    PROMISED = "promised"
    NO_WHATSAPP = "no_whatsapp"
    OPTED_OUT = "opted_out"  # the client is marked "No enviar recordatorios"
    NOT_CONNECTED = "not_connected"
    CONNECTION_ERROR = "connection_error"  # the token was revoked, ...: paused
    TEMPLATE_NOT_APPROVED = "template_not_approved"
    WINDOW_CLOSED = "window_closed"  # the day's window ended before it could go out
    ALREADY_SENT_TODAY = "already_sent_today"
    TENANT_SUSPENDED = "tenant_suspended"


@dataclass(frozen=True, slots=True)
class ReminderEvent:
    tenant_id: UUID
    client_id: UUID
    outcome: Outcome
    day: date  # the business's date
    created_at: datetime
    invoice_id: UUID | None = None
    step_id: UUID | None = None
    offset_days: int | None = None
    reason: str | None = None
    send_id: UUID | None = None
    id: UUID | None = None

    def __post_init__(self) -> None:
        if self.id is None:
            object.__setattr__(self, "id", uuid4())


class SendStatus(StrEnum):
    PENDING = "pending"  # created; the message is going out
    SENT = "sent"
    FAILED = "failed"
    PAUSED = "paused"  # the connection broke while sending; retried another day


@dataclass(frozen=True, slots=True)
class ReminderSend:
    id: UUID
    tenant_id: UUID
    client_id: UUID
    day: date
    status: SendStatus
    template_name: str
    created_at: datetime
    invoice_ids: tuple[UUID, ...] = ()
    # Its step per invoice (what the events record once it goes out).
    steps: tuple[tuple[UUID, UUID, int], ...] = ()  # (invoice_id, step_id, offset_days)
    message_id: UUID | None = None
    payment_request_id: UUID | None = None
    error_code: str | None = None
    sent_at: datetime | None = None
