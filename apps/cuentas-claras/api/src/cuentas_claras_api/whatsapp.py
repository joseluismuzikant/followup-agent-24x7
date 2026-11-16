"""Cuentas Claras's side of the shared WhatsApp connection (followup_platform.whatsapp):
when a number gets connected (Embedded Signup or an admin's manual setup), the business's
reminder templates are created in its WABA; and its webhook counts are kept apart from
inmo24x7's in Salud del sistema."""

from datetime import datetime
from uuid import UUID

from followup_core.messaging.application.connections import ConnectionDraft, SaveConnection
from followup_core.messaging.application.signup import CompleteEmbeddedSignup, SignupRequest
from followup_core.messaging.domain.connection import WhatsAppConnection
from followup_core.messaging.infrastructure.repositories import SqlAlchemyWebhookCounters
from followup_core.scheduling.domain.jobs import JobQueue

from .reminders.application.context import Clock, utc_now
from .reminders.application.templates import ensure_templates_job

# webhook_counters.kind is 20 characters at most.
_COUNTER_KINDS = {"received": "cc_received", "signature_rejected": "cc_sig_rejected"}


class CuentasWebhookCounters:
    def __init__(self, counters: SqlAlchemyWebhookCounters) -> None:
        self._counters = counters

    def increment(self, kind: str, at: datetime) -> None:
        self._counters.increment(_COUNTER_KINDS.get(kind, f"cc_{kind}"[:20]), at)


def _after_connect(queue: JobQueue, connection: WhatsAppConnection, clock: Clock) -> None:
    if connection.is_connected:
        queue.enqueue(ensure_templates_job(connection.tenant_id, clock()))


class SaveConnectionWithTemplates(SaveConnection):
    """The admins' manual setup, then the templates."""

    def __init__(self, inner: SaveConnection, queue: JobQueue, clock: Clock = utc_now) -> None:
        self._inner = inner
        self._queue = queue
        self._clock = clock

    def execute(
        self, tenant_id: UUID, draft: ConnectionDraft, admin_id: UUID | None = None
    ) -> WhatsAppConnection:
        connection = self._inner.execute(tenant_id, draft, admin_id)
        _after_connect(self._queue, connection, self._clock)
        return connection


class SignupWithTemplates(CompleteEmbeddedSignup):
    """Embedded Signup, then the templates."""

    def __init__(
        self, inner: CompleteEmbeddedSignup, queue: JobQueue, clock: Clock = utc_now
    ) -> None:
        self._inner = inner
        self._queue = queue
        self._clock = clock

    def execute(
        self, tenant_id: UUID, request: SignupRequest, actor_profile_id: UUID | None = None
    ) -> WhatsAppConnection:
        connection = self._inner.execute(tenant_id, request, actor_profile_id)
        _after_connect(self._queue, connection, self._clock)
        return connection
