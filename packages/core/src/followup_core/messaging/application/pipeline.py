"""webhook → inbound event → job → agent turn → outbound parts → send job.

The webhook only stores and enqueues (Meta gets its 200 in milliseconds and never waits for
the model). A worker runs the turn after a short debounce, so a burst of messages gets one
answer, and sending is a job of its own, so a Meta outage never rolls back a turn.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from followup_core.conversation.application.threads import (
    Clock,
    HandleIncomingMessage,
    ReplyWithoutAgent,
    utc_now,
)
from followup_core.conversation.domain.repositories import ThreadLock
from followup_core.conversation.domain.thread import (
    Author,
    Channel,
    InboundPart,
    Message,
    ThreadKey,
)
from followup_core.scheduling.domain.jobs import Job, JobQueue, NewJob, Reschedule, RetryLater

from ..domain.connection import WhatsAppConnection
from ..domain.events import EventStatus, InboundEvent
from ..domain.outbound import (
    OUTSIDE_SERVICE_WINDOW,
    UNREADABLE_REPLY,
    DeliveryStatus,
    MessageRenderer,
    OutboundPart,
    SendError,
    WhatsAppSender,
    within_service_window,
)
from ..domain.phones import display, to_e164
from ..domain.repositories import ConnectionRepository, InboundEventRepository, OutboundRepository
from ..domain.webhook import parse_webhook

logger = logging.getLogger("followup.whatsapp")

PROCESS_JOB = "whatsapp.process"
SEND_JOB = "whatsapp.send"
MARK_READ_JOB = "whatsapp.mark_read"
PURGE_JOB = "whatsapp.purge_payloads"
PAYLOAD_RETENTION = timedelta(days=30)
DEFAULT_DEBOUNCE = timedelta(seconds=3)


@dataclass(frozen=True, slots=True)
class IngestResult:
    queued: int = 0
    duplicates: int = 0
    ignored: int = 0
    statuses: int = 0


class ApplyDeliveryStatus:
    """sent / delivered / read / failed for one of our messages, by wamid. Statuses only move
    forward; unknown wamids (another app's messages) are ignored."""

    def __init__(self, outbound: OutboundRepository) -> None:
        self._outbound = outbound

    def execute(self, wamid: str, status: str, at: datetime, error_code: str | None = None) -> bool:
        try:
            parsed = DeliveryStatus(status)
        except ValueError:
            return False
        return self._outbound.apply_status(wamid, parsed, error_code, at)


class IngestWebhook:
    """The webhook request: store each message once and enqueue its processing. No model,
    no Meta call. Duplicates (Meta retries) are dropped by the unique wamid."""

    def __init__(
        self,
        connections: ConnectionRepository,
        events: InboundEventRepository,
        statuses: ApplyDeliveryStatus,
        queue: JobQueue,
        debounce: timedelta = DEFAULT_DEBOUNCE,
        clock: Clock = utc_now,
    ) -> None:
        self._connections = connections
        self._events = events
        self._statuses = statuses
        self._queue = queue
        self._debounce = debounce
        self._clock = clock

    def execute(self, payload: Mapping[str, Any]) -> IngestResult:
        messages, statuses = parse_webhook(payload)
        now = self._clock()
        queued = duplicates = ignored = 0
        for message in messages:
            connection = self._connections.get_by_phone_number_id(message.phone_number_id)
            tenant_id = connection.tenant_id if connection and connection.is_connected else None
            event = InboundEvent(
                id=uuid4(),
                wamid=message.wamid,
                tenant_id=tenant_id,
                phone_number_id=message.phone_number_id,
                wa_id=message.wa_id,
                type=message.type,
                sent_at=message.sent_at,
                status=EventStatus.PENDING if tenant_id else EventStatus.IGNORED,
                created_at=now,
                text=message.text,
                choice_id=message.choice_id,
            )
            if not self._events.add(event, message.raw):
                duplicates += 1
                continue
            if tenant_id is None:
                ignored += 1
                logger.warning(
                    "whatsapp_unknown_number",
                    extra={"phone_number_id": message.phone_number_id, "event_id": str(event.id)},
                )
                continue
            self._queue.enqueue(
                NewJob(
                    PROCESS_JOB,
                    {"event_id": str(event.id)},
                    run_at=now + self._debounce,
                    dedupe_key=f"wa-in:{message.wamid}",
                )
            )
            queued += 1
        applied = sum(
            self._statuses.execute(item.wamid, item.status, item.at, item.error_code)
            for item in statuses
        )
        return IngestResult(queued, duplicates, ignored, applied)


def channel_contact(wa_id: str) -> str | None:
    """The visitor's own number, as the lead's contact."""
    e164 = to_e164(wa_id)
    return display(e164) if e164 else None


class QueueOutbound:
    """Stores every part of the given messages as queued and enqueues ONE send job for them,
    in order. Used for an agent turn and for a message written by the team. System messages
    (the hand-off event) are never sent to the lead."""

    def __init__(self, outbound: OutboundRepository, render: MessageRenderer, queue: JobQueue):
        self._outbound = outbound
        self._render = render
        self._queue = queue

    def __call__(self, messages: Sequence[Message], wa_id: str) -> None:
        parts: list[OutboundPart] = []
        sendable: list[UUID] = []
        for message in messages:
            if message.author is Author.SYSTEM:
                continue
            bodies = self._render(message)
            for index, body in enumerate(bodies):
                parts.append(
                    OutboundPart(uuid4(), message.id, index, wa_id, body, DeliveryStatus.QUEUED)
                )
            if bodies:
                sendable.append(message.id)
        if not parts:
            return
        self._outbound.add(parts)
        self._queue.enqueue(
            NewJob(
                SEND_JOB,
                {"message_ids": [str(item) for item in sendable]},
                dedupe_key=f"wa-send:{sendable[0]}",
            )
        )


class ProcessInbound:
    """One job per inbound message; the first one that runs after the burst settles takes
    every pending message of the conversation, in order, and answers them with one turn."""

    def __init__(
        self,
        events: InboundEventRepository,
        connections: ConnectionRepository,
        outbound: OutboundRepository,
        lock: ThreadLock,
        handle: HandleIncomingMessage,
        reply_without_agent: ReplyWithoutAgent,
        render: MessageRenderer,
        queue: JobQueue,
        debounce: timedelta = DEFAULT_DEBOUNCE,
        clock: Clock = utc_now,
    ) -> None:
        self._events = events
        self._connections = connections
        self._lock = lock
        self._handle = handle
        self._reply_without_agent = reply_without_agent
        self._queue_outbound = QueueOutbound(outbound, render, queue)
        self._queue = queue
        self._debounce = debounce
        self._clock = clock

    def __call__(self, job: Job) -> Reschedule | None:
        event = self._events.get(UUID(job.payload["event_id"]))
        if event is None or event.tenant_id is None or event.status is not EventStatus.PENDING:
            return None
        key = ThreadKey(event.tenant_id, Channel.WHATSAPP, event.wa_id)
        # The same per-thread lock as every turn: two jobs of one conversation run in order.
        self._lock.acquire(key)
        pending = self._events.pending_for(event.tenant_id, event.wa_id)
        if not pending:
            return None
        newest = max(item.created_at for item in pending)
        if self._clock() - newest < self._debounce:
            # Still typing: answer once the burst settles.
            return Reschedule(newest + self._debounce)

        parts = [
            InboundPart(
                text=item.text or "",
                received_at=item.sent_at,
                content_type="text" if item.is_text else item.type,
            )
            for item in pending
        ]
        if any(item.is_text for item in pending):
            taps = [item.choice_id for item in pending if item.choice_id]
            turn = self._handle.execute(
                key,
                parts,
                choice_id=taps[-1] if taps else None,
                visitor_contact=channel_contact(event.wa_id),
            )
            replies = list(turn.outbound)
        else:
            fixed = self._reply_without_agent.execute(key, parts, UNREADABLE_REPLY).outbound
            replies = [fixed] if fixed else []
        self._events.mark([item.id for item in pending], EventStatus.PROCESSED)

        # Nothing to send while the team has the conversation (the turn stored only).
        self._queue_outbound(replies, event.wa_id)
        last = pending[-1]
        self._queue.enqueue(
            NewJob(
                MARK_READ_JOB,
                {"tenant_id": str(event.tenant_id), "wamid": last.wamid},
                dedupe_key=f"wa-read:{last.wamid}",
                max_attempts=3,
            )
        )
        connection = self._connections.get_by_tenant(event.tenant_id)
        if connection is not None:
            self._connections.mark_inbound(connection.id, last.sent_at)
        return None


SenderFor = Callable[[WhatsAppConnection], WhatsAppSender]


class SendQueued:
    """Sends a turn's parts in order. Parts that already have a wamid are skipped, so a
    retry after a 429 or a 5xx never sends anything twice. Permanent errors mark the part
    failed with Meta's code and the next part still goes out."""

    def __init__(
        self,
        outbound: OutboundRepository,
        connections: ConnectionRepository,
        sender_for: SenderFor,
        clock: Clock = utc_now,
    ) -> None:
        self._outbound = outbound
        self._connections = connections
        self._sender_for = sender_for
        self._clock = clock

    def __call__(self, job: Job) -> RetryLater | None:
        message_ids = [UUID(item) for item in job.payload["message_ids"]]
        parts = [part for part in self._outbound.for_messages(message_ids) if not part.wamid]
        if not parts:
            return None
        tenant_id = self._outbound.tenant_of(parts[0].message_id)
        connection = self._connections.get_by_tenant(tenant_id) if tenant_id else None
        now = self._clock()
        if connection is None or not connection.is_connected:
            for part in parts:
                self._outbound.mark_failed(part.id, "not_connected", now)
            return None
        sender = self._sender_for(connection)
        for part in parts:
            if part.status is not DeliveryStatus.QUEUED:
                continue
            # Templates are the one kind of message allowed outside the 24-hour window.
            is_template = part.body.get("type") == "template"
            last_inbound = self._outbound.last_inbound_at(part.message_id)
            if not is_template and not within_service_window(last_inbound, now):
                self._outbound.mark_failed(part.id, OUTSIDE_SERVICE_WINDOW, now)
                continue
            try:
                wamid = sender.send(connection, part.wa_id, part.body)
            except SendError as error:
                if error.retryable:
                    return RetryLater(f"meta_{error.code}")
                self._outbound.mark_failed(part.id, error.code, now)
                logger.warning(
                    "whatsapp_send_failed",
                    extra={"message_id": str(part.message_id), "meta_code": error.code},
                )
                continue
            self._outbound.mark_sent(part.id, wamid, now)
        return None


class OutsideServiceWindowError(Exception):
    pass


def send_template(
    sender: WhatsAppSender,
    connection: WhatsAppConnection,
    to: str,
    parameters: Sequence[str] = (),
    *,
    name: str | None = None,
    language: str | None = None,
) -> str:
    """A template message, the only kind allowed outside the 24-hour window. Defaults to
    the connection's template (the visit confirmation one, used on Day 6)."""
    return sender.send_template(
        connection,
        to,
        name or connection.template_name,
        language or connection.template_language,
        parameters,
    )


class MarkRead:
    def __init__(self, connections: ConnectionRepository, sender_for: SenderFor) -> None:
        self._connections = connections
        self._sender_for = sender_for

    def __call__(self, job: Job) -> None:
        connection = self._connections.get_by_tenant(UUID(job.payload["tenant_id"]))
        if connection is None or not connection.is_connected:
            return
        try:
            self._sender_for(connection).mark_read(connection, job.payload["wamid"])
        except SendError as error:
            # Not worth retrying: the conversation goes on without the blue ticks.
            logger.warning("whatsapp_mark_read_failed", extra={"meta_code": error.code})


class PurgePayloads:
    """Raw webhook payloads hold personal data: dropped after 30 days (rows stay). Runs once a
    day: each run schedules the next one (the worker also enqueues one when it starts, in case
    the chain was lost; the dedupe key keeps it to one per day)."""

    def __init__(
        self, events: InboundEventRepository, queue: JobQueue, clock: Clock = utc_now
    ) -> None:
        self._events = events
        self._queue = queue
        self._clock = clock

    def __call__(self, job: Job) -> None:
        now = self._clock()
        purged = self._events.purge_payloads(now - PAYLOAD_RETENTION)
        logger.info("whatsapp_payloads_purged", extra={"count": purged})
        self._queue.enqueue(purge_job(now + timedelta(days=1), run_at=now + timedelta(days=1)))


def purge_job(day: datetime, run_at: datetime | None = None) -> NewJob:
    return NewJob(
        PURGE_JOB, {}, run_at=run_at, dedupe_key=f"wa-purge:{day:%Y-%m-%d}", max_attempts=3
    )
