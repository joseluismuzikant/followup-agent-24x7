"""Local development without Meta: nothing leaves the machine. Each "sent" message gets a
fake wamid, and its sent → delivered → read updates arrive a second apart as jobs that go
through the same status code as Meta's webhook."""

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from followup_core.scheduling.domain.jobs import JobQueue, NewJob

from ..domain.connection import WhatsAppConnection

logger = logging.getLogger("followup.whatsapp")

LOG_STATUS_JOB = "whatsapp.log_status"
_STATUSES = ("sent", "delivered", "read")


class LogSender:
    def __init__(
        self, queue: JobQueue, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self._queue = queue
        self._clock = clock

    def send(self, connection: WhatsAppConnection, to: str, body: Mapping[str, Any]) -> str:
        wamid = f"wamid.log.{uuid4().hex}"
        logger.info(
            "whatsapp_log_send",
            extra={
                "tenant_id": str(connection.tenant_id),
                "wamid": wamid,
                "type": body.get("type"),
            },
        )
        now = self._clock()
        for step, status in enumerate(_STATUSES, start=1):
            self._queue.enqueue(
                NewJob(
                    LOG_STATUS_JOB,
                    {"wamid": wamid, "status": status},
                    run_at=now + timedelta(seconds=step),
                    max_attempts=3,
                )
            )
        return wamid

    def send_template(
        self,
        connection: WhatsAppConnection,
        to: str,
        name: str,
        language: str,
        parameters: Sequence[str] = (),
    ) -> str:
        return self.send(connection, to, {"type": "template", "template": {"name": name}})

    def mark_read(self, connection: WhatsAppConnection, wamid: str) -> None:
        logger.info("whatsapp_log_mark_read", extra={"tenant_id": str(connection.tenant_id)})


class RecordingWhatsAppSender:
    """For tests: keeps what would have been sent and can fail on demand."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.read: list[str] = []
        self.failures: list[Exception] = []

    def send(self, connection: WhatsAppConnection, to: str, body: Mapping[str, Any]) -> str:
        if self.failures:
            raise self.failures.pop(0)
        self.sent.append((to, dict(body)))
        return f"wamid.rec.{len(self.sent)}"

    def send_template(
        self,
        connection: WhatsAppConnection,
        to: str,
        name: str,
        language: str,
        parameters: Sequence[str] = (),
    ) -> str:
        return self.send(
            connection,
            to,
            {"type": "template", "template": {"name": name, "language": {"code": language}}},
        )

    def mark_read(self, connection: WhatsAppConnection, wamid: str) -> None:
        self.read.append(wamid)
