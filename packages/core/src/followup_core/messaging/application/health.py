"""Connection health: an auth error from Meta stops sending at once (no retry loop), queued
messages wait for the customer to reconnect, and reconnecting sends them in order. A job
reads every Cloud connection every 6 hours, and Meta's account_update webhook moves the
state too."""

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

from followup_core.conversation.application.threads import Clock, utc_now
from followup_core.scheduling.domain.jobs import Job, JobQueue, NewJob
from followup_core.tenancy.domain.audit import (
    ActorKind,
    AuditAction,
    AuditEvent,
    AuditLog,
    hourly_key,
)

from ..domain.connection import BusinessVerification, SenderKind, WhatsAppConnection
from ..domain.meta_errors import MetaErrorKind, classify
from ..domain.outbound import SendError
from ..domain.repositories import ConnectionRepository, OutboundRepository
from ..domain.webhook import AccountUpdate
from .connections import GraphPort

logger = logging.getLogger("followup.whatsapp")

SEND_JOB = "whatsapp.send"
HEALTH_SWEEP_JOB = "whatsapp.health_sweep"
HEALTH_CHECK_JOB = "whatsapp.health_check"
HEALTH_INTERVAL = timedelta(hours=6)

# Account problems that also stop every send (the auth ones always do).
_STOPPING_CODES = frozenset(
    {"account_restricted", "account_disabled", "account_deleted", "number_offboarded"}
)

TenantIsActive = Callable[[UUID], bool]


def always_active(_tenant_id: UUID) -> bool:
    return True


def stops_sending(code: str) -> bool:
    error = classify(code)
    return error.kind is MetaErrorKind.AUTH or error.code in _STOPPING_CODES


class ConnectionHealth:
    """The one place that moves a connection into and out of the error state."""

    def __init__(
        self,
        connections: ConnectionRepository,
        outbound: OutboundRepository,
        queue: JobQueue,
        audit: AuditLog,
        clock: Clock = utc_now,
    ) -> None:
        self._connections = connections
        self._outbound = outbound
        self._queue = queue
        self._audit = audit
        self._clock = clock

    def failed(self, connection: WhatsAppConnection, code: str) -> WhatsAppConnection:
        now = self._clock()
        updated = connection.with_error(code, now)
        self._connections.save(updated)
        self._audit.record(
            AuditEvent(
                connection.tenant_id,
                now,
                ActorKind.SYSTEM,
                AuditAction.WHATSAPP_ERROR,
                {"meta_code": code[:40]},
                dedupe_key=hourly_key(AuditAction.WHATSAPP_ERROR, connection.tenant_id, code, now),
            )
        )
        # An error: the number stopped answering until someone reconnects it.
        logger.error(
            "whatsapp_connection_error",
            extra={"tenant_id": str(connection.tenant_id), "meta_code": code},
        )
        return updated

    def send_failed(self, tenant_id: UUID, code: str) -> None:
        """A message that could not go out for a reason of its own (one per code and hour)."""
        now = self._clock()
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.SYSTEM,
                AuditAction.SEND_FAILURE,
                {"meta_code": code[:40]},
                dedupe_key=hourly_key(AuditAction.SEND_FAILURE, tenant_id, code, now),
            )
        )

    def recovered(self, connection: WhatsAppConnection, source: str) -> WhatsAppConnection:
        """Back to connected (when it was failing), then send what waited."""
        updated = connection
        if connection.is_failing:
            now = self._clock()
            updated = connection.recovered(now)
            self._connections.save(updated)
            self._audit.record(
                AuditEvent(
                    connection.tenant_id,
                    now,
                    ActorKind.SYSTEM,
                    AuditAction.WHATSAPP_RECOVERED,
                    {"source": source},
                )
            )
        self.resume(connection.tenant_id)
        return updated

    def resume(self, tenant_id: UUID) -> int:
        """Waiting parts go back to queued, sent by ONE job in conversation order. The 24 h
        window still applies when they go out."""
        message_ids = self._outbound.waiting_messages(tenant_id)
        if not message_ids:
            return 0
        now = self._clock()
        self._outbound.requeue(message_ids, now)
        self._queue.enqueue(
            NewJob(
                SEND_JOB,
                {"message_ids": [str(item) for item in message_ids]},
                dedupe_key=f"wa-resume:{message_ids[0]}:{now:%Y%m%d%H%M%S}",
            )
        )
        return len(message_ids)


def _slot(at: datetime) -> datetime:
    hours = at.hour - at.hour % int(HEALTH_INTERVAL.total_seconds() // 3600)
    return at.replace(hour=hours, minute=0, second=0, microsecond=0)


def health_sweep_job(at: datetime) -> NewJob:
    """The sweep of the 6-hour slot that contains `at` (one per slot, whoever enqueues it)."""
    slot = _slot(at)
    return NewJob(
        HEALTH_SWEEP_JOB,
        {},
        run_at=max(slot, at),
        dedupe_key=f"wa-health-sweep:{slot:%Y%m%d%H}",
        max_attempts=3,
    )


class HealthSweep:
    """Every 6 hours: one check job per Cloud connection of an active business. Each run
    schedules the next slot (the worker also enqueues the current one when it starts)."""

    def __init__(
        self,
        connections: ConnectionRepository,
        queue: JobQueue,
        is_active: TenantIsActive = always_active,
        clock: Clock = utc_now,
    ) -> None:
        self._connections = connections
        self._queue = queue
        self._is_active = is_active
        self._clock = clock

    def __call__(self, job: Job) -> None:
        now = self._clock()
        slot = _slot(now)
        checked = 0
        for connection in self._connections.cloud_connections():
            if not self._is_active(connection.tenant_id):
                continue
            self._queue.enqueue(
                NewJob(
                    HEALTH_CHECK_JOB,
                    {"tenant_id": str(connection.tenant_id)},
                    dedupe_key=f"wa-health:{connection.tenant_id}:{slot:%Y%m%d%H}",
                    max_attempts=3,
                )
            )
            checked += 1
        logger.info("whatsapp_health_sweep", extra={"connections": checked})
        self._queue.enqueue(health_sweep_job(slot + HEALTH_INTERVAL))


class HealthCheck:
    """Reads the number's status, quality and the business verification. An auth error puts
    the connection in error; a success clears an error that a check or a send left."""

    def __init__(
        self,
        connections: ConnectionRepository,
        graph_for: Callable[[WhatsAppConnection], GraphPort],
        health: ConnectionHealth,
        is_active: TenantIsActive = always_active,
        clock: Clock = utc_now,
    ) -> None:
        self._connections = connections
        self._graph_for = graph_for
        self._health = health
        self._is_active = is_active
        self._clock = clock

    def __call__(self, job: Job) -> None:
        tenant_id = UUID(job.payload["tenant_id"])
        connection = self._connections.get_by_tenant(tenant_id)
        if (
            connection is None
            or connection.sender is not SenderKind.CLOUD
            or not self._is_active(tenant_id)
        ):
            return
        self.check(connection)

    def check(self, connection: WhatsAppConnection) -> WhatsAppConnection:
        graph = self._graph_for(connection)
        try:
            info = graph.phone_number(connection)
        except SendError as error:
            if stops_sending(error.code):
                return self._health.failed(connection, error.code)
            logger.warning("whatsapp_health_check_failed", extra={"meta_code": error.code})
            return connection
        verification = graph.business_verification(connection)
        updated = replace(
            connection,
            display_phone_number=info.display_phone_number or connection.display_phone_number,
            verified_name=info.verified_name or connection.verified_name,
            quality_rating=info.quality_rating or connection.quality_rating,
            name_status=info.name_status or connection.name_status,
            business_verification=(
                connection.business_verification
                if verification is BusinessVerification.UNKNOWN
                else verification
            ),
            last_health_check_at=self._clock(),
        )
        self._connections.save(updated)
        # Only errors a successful read disproves (the token works again).
        if updated.is_failing and classify(updated.last_error_code).kind is MetaErrorKind.AUTH:
            return self._health.recovered(updated, "health_check")
        return updated


# account_update events and what they mean for the connection.
_STOPS = {
    "PARTNER_APP_UNINSTALLED": "app_removed",
    "PARTNER_REMOVED": "app_removed",
    "ACCOUNT_DELETED": "account_deleted",
    "ACCOUNT_OFFBOARDED": "number_offboarded",
}
_CERTIFICATION = {
    "APPROVED": BusinessVerification.VERIFIED,
    "FAILED": BusinessVerification.FAILED,
    "PENDING": BusinessVerification.PENDING,
}


class ApplyAccountUpdate:
    """Meta's account_update webhook for a connected WABA. Restrictions and violations are
    recorded only: a send that is really blocked fails with its own code and stops there."""

    def __init__(
        self,
        connections: ConnectionRepository,
        health: ConnectionHealth,
        audit: AuditLog,
        clock: Clock = utc_now,
    ) -> None:
        self._connections = connections
        self._health = health
        self._audit = audit
        self._clock = clock

    def execute(self, update: AccountUpdate) -> bool:
        connection = self._connections.get_by_waba_id(update.waba_id)
        if connection is None:
            return False
        state = update.ban_state or update.certification_status
        self._audit.record(
            AuditEvent(
                connection.tenant_id,
                self._clock(),
                ActorKind.SYSTEM,
                AuditAction.WHATSAPP_ACCOUNT_UPDATE,
                {"event": update.event[:60], "state": (state or "")[:40] or None},
            )
        )
        if update.event in _STOPS:
            self._health.failed(connection, _STOPS[update.event])
        elif update.event == "DISABLED_UPDATE":
            if update.ban_state == "DISABLE":
                self._health.failed(connection, "account_disabled")
            elif (
                update.ban_state == "REINSTATE" and connection.last_error_code == "account_disabled"
            ):
                self._health.recovered(connection, "account_update")
        elif update.event == "ACCOUNT_RECONNECTED":
            if connection.last_error_code == "number_offboarded":
                self._health.recovered(connection, "account_update")
        elif update.event == "PARTNER_CLIENT_CERTIFICATION_STATUS_UPDATE":
            verification = _CERTIFICATION.get(update.certification_status or "")
            if verification is not None:
                self._connections.save(
                    replace(
                        connection, business_verification=verification, updated_at=self._clock()
                    )
                )
        return True
