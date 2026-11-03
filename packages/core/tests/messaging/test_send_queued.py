"""Sending a turn's parts with a recording sender and in-memory repositories."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from followup_core.messaging.application.pipeline import (
    PURGE_JOB,
    PurgePayloads,
    SendQueued,
    send_template,
)
from followup_core.messaging.domain.connection import (
    ConnectionStatus,
    SenderKind,
    WhatsAppConnection,
)
from followup_core.messaging.domain.outbound import (
    DeliveryStatus,
    OutboundPart,
    SendError,
    template_body,
)
from followup_core.messaging.infrastructure.log_sender import RecordingWhatsAppSender
from followup_core.scheduling.domain.jobs import Job, JobStatus, NewJob, RetryLater

NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)
TENANT = uuid4()


def connection(**changes) -> WhatsAppConnection:
    base = WhatsAppConnection(
        id=uuid4(),
        tenant_id=TENANT,
        phone_number_id="pn-1",
        waba_id="waba-1",
        access_token_encrypted="k1:x",
        sender=SenderKind.CLOUD,
        template_name="visita_confirmada",
        template_language="es_AR",
        status=ConnectionStatus.CONNECTED,
        updated_at=NOW,
    )
    return replace(base, **changes)


class Connections:
    def __init__(self, item: WhatsAppConnection) -> None:
        self.item = item

    def get_by_tenant(self, tenant_id: UUID) -> WhatsAppConnection | None:
        return self.item if self.item.tenant_id == tenant_id else None

    def get_by_phone_number_id(self, phone_number_id: str) -> WhatsAppConnection | None:
        return self.item

    def save(self, connection: WhatsAppConnection) -> None:
        self.item = connection

    def mark_inbound(self, connection_id: UUID, at: datetime) -> None: ...

    def get_by_waba_id(self, waba_id: str) -> WhatsAppConnection | None:
        return self.item if self.item.waba_id == waba_id else None

    def cloud_connections(self) -> Sequence[WhatsAppConnection]:
        return [self.item] if self.item.sender is SenderKind.CLOUD else []


class Outbound:
    def __init__(self, parts: list[OutboundPart], last_inbound: datetime | None) -> None:
        self.parts = {part.id: part for part in parts}
        self.last_inbound = last_inbound

    def add(self, parts: Sequence[OutboundPart]) -> None: ...

    def for_messages(self, message_ids: Sequence[UUID]) -> Sequence[OutboundPart]:
        return [p for p in self.parts.values() if p.message_id in message_ids]

    def mark_sent(self, part_id: UUID, wamid: str, at: datetime) -> None:
        self.parts[part_id] = replace(self.parts[part_id], wamid=wamid)

    def mark_failed(self, part_id: UUID, code: str, at: datetime) -> None:
        self.parts[part_id] = replace(
            self.parts[part_id], status=DeliveryStatus.FAILED, error_code=code
        )

    def mark_waiting(self, part_ids: Sequence[UUID], code: str, at: datetime) -> None:
        for part_id in part_ids:
            self.parts[part_id] = replace(
                self.parts[part_id], status=DeliveryStatus.WAITING, error_code=code
            )

    def waiting_messages(self, tenant_id: UUID) -> Sequence[UUID]:
        waiting = [p.message_id for p in self.parts.values() if p.status is DeliveryStatus.WAITING]
        return list(dict.fromkeys(waiting))

    def requeue(self, message_ids: Sequence[UUID], at: datetime) -> None:
        for part in list(self.parts.values()):
            if part.message_id in message_ids and part.status is DeliveryStatus.WAITING:
                self.parts[part.id] = replace(part, status=DeliveryStatus.QUEUED, error_code=None)

    def apply_status(self, wamid, status, error_code, at) -> bool:
        return False

    def last_inbound_at(self, message_id: UUID) -> datetime | None:
        return self.last_inbound

    def tenant_of(self, message_id: UUID) -> UUID | None:
        return TENANT

    def statuses(self, message_ids) -> Mapping[UUID, Sequence[DeliveryStatus]]:
        return {}


MESSAGE = uuid4()


def parts(count: int = 3) -> list[OutboundPart]:
    return [
        OutboundPart(
            uuid4(),
            MESSAGE,
            n,
            "5491155550188",
            {"type": "text", "text": {"body": f"parte {n}"}},
            DeliveryStatus.QUEUED,
        )
        for n in range(count)
    ]


def job() -> Job:
    return Job(
        uuid4(), "whatsapp.send", {"message_ids": [str(MESSAGE)]}, NOW, JobStatus.RUNNING, 1, 8
    )


def run(
    outbound: Outbound, sender: RecordingWhatsAppSender, conn: WhatsAppConnection | None = None
):
    use_case = SendQueued(
        outbound, Connections(conn or connection()), lambda _c: sender, lambda: NOW
    )
    return use_case(job())


def bodies(sender: RecordingWhatsAppSender) -> list[str]:
    return [body["text"]["body"] for _, body in sender.sent]


def test_parts_go_out_in_order_to_the_wa_id() -> None:
    sender = RecordingWhatsAppSender()
    outbound = Outbound(parts(), NOW - timedelta(minutes=5))

    assert run(outbound, sender) is None

    assert bodies(sender) == ["parte 0", "parte 1", "parte 2"]
    assert {to for to, _ in sender.sent} == {"5491155550188"}
    assert all(part.wamid for part in outbound.parts.values())


def test_a_5xx_keeps_what_was_sent_and_retries_only_the_rest() -> None:
    sender = RecordingWhatsAppSender()
    outbound = Outbound(parts(), NOW - timedelta(minutes=5))
    # First part fails with a 503: nothing is marked, the job retries.
    sender.failures = [SendError("http_503", retryable=True, http_status=503)]
    assert run(outbound, sender) == RetryLater("meta_http_503")
    assert bodies(sender) == []

    assert run(outbound, sender) is None
    assert bodies(sender) == ["parte 0", "parte 1", "parte 2"]
    # A second run after success sends nothing again.
    assert run(outbound, sender) is None
    assert len(sender.sent) == 3


def test_a_permanent_error_fails_that_part_and_the_rest_still_go() -> None:
    sender = RecordingWhatsAppSender()
    outbound = Outbound(parts(), NOW - timedelta(minutes=5))
    sender.failures = [SendError("131026", retryable=False, http_status=400)]

    assert run(outbound, sender) is None

    statuses = [(p.part, p.status, p.error_code) for p in outbound.parts.values()]
    assert statuses[0] == (0, DeliveryStatus.FAILED, "131026")
    assert bodies(sender) == ["parte 1", "parte 2"]


def test_outside_the_24_hour_window_nothing_is_sent() -> None:
    sender = RecordingWhatsAppSender()
    outbound = Outbound(parts(1), NOW - timedelta(hours=25))

    run(outbound, sender)

    assert sender.sent == []
    (part,) = outbound.parts.values()
    assert (part.status, part.error_code) == (DeliveryStatus.FAILED, "outside_service_window")


def test_a_template_part_goes_out_even_outside_the_window() -> None:
    sender = RecordingWhatsAppSender()
    (part,) = parts(1)
    template = template_body("confirmacion_visita", "es_AR", ["Ana", "Gorriti 4800", "sáb"])
    outbound = Outbound([replace(part, body=template)], NOW - timedelta(days=3))

    run(outbound, sender)

    assert sender.sent == [("5491155550188", template)]


def test_a_disconnected_number_fails_the_parts() -> None:
    sender = RecordingWhatsAppSender()
    outbound = Outbound(parts(1), NOW)

    run(outbound, sender, connection(status=ConnectionStatus.DISCONNECTED))

    assert sender.sent == []
    assert [p.error_code for p in outbound.parts.values()] == ["not_connected"]


def test_templates_use_the_connection_template_by_default() -> None:
    sender = RecordingWhatsAppSender()

    send_template(sender, connection(), "5491155550188", ["jueves 6/11, 10:30"])
    send_template(sender, connection(), "5491155550188", name="hello_world", language="en_US")

    assert [body["template"] for _, body in sender.sent] == [
        {"name": "visita_confirmada", "language": {"code": "es_AR"}},
        {"name": "hello_world", "language": {"code": "en_US"}},
    ]


class Queue:
    def __init__(self) -> None:
        self.jobs: list[NewJob] = []

    def enqueue(self, job: NewJob) -> bool:
        self.jobs.append(job)
        return True


class Events:
    def __init__(self) -> None:
        self.before: datetime | None = None

    def purge_payloads(self, before: datetime) -> int:
        self.before = before
        return 2


def test_the_purge_runs_daily_and_keeps_30_days() -> None:
    events, queue = Events(), Queue()

    PurgePayloads(events, queue, lambda: NOW)(  # type: ignore[arg-type]
        Job(uuid4(), PURGE_JOB, {}, NOW, JobStatus.RUNNING, 1, 3)
    )

    assert events.before == NOW - timedelta(days=30)
    (next_run,) = queue.jobs
    assert (next_run.kind, next_run.run_at, next_run.dedupe_key) == (
        PURGE_JOB,
        NOW + timedelta(days=1),
        "wa-purge:2026-11-04",
    )
