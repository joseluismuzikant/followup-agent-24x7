"""Backoffice (platform admins): "Eliminar datos de un contacto", "No contactar" by phone,
and "Cerrar cuenta y eliminar datos" (a background job).

The landing promises both (www.inmo24x7.com/eliminacion-de-datos): stop messages within 2
business days of a "BAJA", delete a person's or an agency's data within 5 business days.
Audit events say what happened, when and by which admin, with counts only: never the phone,
the name or a hash of them (a phone's hash can be reversed by trying every number).
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from followup_core.identity.domain.account import AccountDirectory
from followup_core.messaging.application.connections import GraphPort
from followup_core.messaging.application.opt_out import ContactOptOut
from followup_core.messaging.domain.connection import WhatsAppConnection
from followup_core.messaging.domain.opt_out import OptOutSource
from followup_core.messaging.domain.repositories import ConnectionRepository
from followup_core.scheduling.domain.jobs import Job, JobQueue, NewJob, Reschedule
from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog

from ..audit import InmoAction
from .domain import (
    BusinessNotFoundError,
    ClosureSummary,
    ConfirmationMismatchError,
    ContactNotFoundError,
    ContactSummary,
    ErasedCounts,
    PhoneInvalidError,
    PlatformBusinessError,
    confirms,
    wa_id_for,
)
from .erasure import BusinessRow, SqlAlchemyErasure

logger = logging.getLogger("inmo24x7.privacy")

CLOSE_ACCOUNT_JOB = "tenant.close"
# Deletes the finished closing job's own row: its payload names the business. Its own
# payload holds only that job's id.
CLOSE_CLEANUP_JOB = "tenant.close_cleanup"
CLEANUP_RETRY = timedelta(minutes=1)
Clock = Callable[[], datetime]


def _business(erasure: SqlAlchemyErasure, tenant_id: UUID) -> BusinessRow:
    business = erasure.business(tenant_id)
    if business is None:
        raise BusinessNotFoundError(str(tenant_id))
    return business


def _counts(counts: ErasedCounts) -> dict[str, int]:
    return {
        "leads": counts.leads,
        "threads": counts.threads,
        "messages": counts.messages,
        "visits": counts.visits,
        "llm_calls_unlinked": counts.llm_calls_unlinked,
    }


class FindContacts:
    """By phone (any format, or part of it) or by name, WhatsApp contacts only."""

    def __init__(self, erasure: SqlAlchemyErasure) -> None:
        self._erasure = erasure

    def execute(self, tenant_id: UUID, query: str) -> list[ContactSummary]:
        _business(self._erasure, tenant_id)
        query = query.strip()
        digits = "".join(char for char in query if char.isdigit())
        exact = wa_id_for(query) if len(digits) >= 8 else None
        words = "" if digits else query
        if not exact and len(digits) < 6 and len(words) < 2:
            return []
        return self._erasure.contacts(
            tenant_id,
            wa_ids=[exact] if exact else [],
            digits=digits if len(digits) >= 6 else "",
            words=words,
        )


class DeleteContactData:
    """Everything of one contact in one business: leads, their history, conditions and
    visits, the conversation and its LangGraph checkpoints, WhatsApp events and messages,
    and their pending jobs. The do-not-contact flag stays, so a "BAJA" is still honored."""

    def __init__(self, erasure: SqlAlchemyErasure, audit: AuditLog, clock: Clock) -> None:
        self._erasure = erasure
        self._audit = audit
        self._clock = clock

    def execute(
        self, admin_id: UUID, tenant_id: UUID, wa_id: str, confirmation: str
    ) -> ErasedCounts:
        _business(self._erasure, tenant_id)
        if not confirms(confirmation, wa_id):
            raise ConfirmationMismatchError(str(tenant_id))
        if not self._erasure.contacts(tenant_id, wa_ids=[wa_id]):
            raise ContactNotFoundError(str(tenant_id))
        counts = self._erasure.delete_contact(tenant_id, wa_id)
        self._audit.record(
            AuditEvent(
                tenant_id,
                self._clock(),
                ActorKind.ADMIN,
                InmoAction.CONTACT_DATA_DELETED,
                _counts(counts),
                actor_profile_id=admin_id,
            )
        )
        logger.info("contact_data_deleted", extra={"tenant_id": str(tenant_id)})
        return counts


class SetContactDoNotContact:
    """ "Marcar como no contactar" / "Quitar" by phone, for a request that arrived by email or
    phone (the number may never have written)."""

    def __init__(self, erasure: SqlAlchemyErasure, opt_out: ContactOptOut) -> None:
        self._erasure = erasure
        self._opt_out = opt_out

    def execute(self, admin_id: UUID, tenant_id: UUID, phone: str, blocked: bool) -> str:
        _business(self._erasure, tenant_id)
        wa_id = wa_id_for(phone)
        if wa_id is None:
            raise PhoneInvalidError(str(tenant_id))
        if blocked:
            self._opt_out.block(tenant_id, wa_id, OptOutSource.ADMIN, profile_id=admin_id)
        else:
            self._opt_out.lift(tenant_id, wa_id, OptOutSource.ADMIN, profile_id=admin_id)
        return wa_id


class GetClosureSummary:
    def __init__(self, erasure: SqlAlchemyErasure) -> None:
        self._erasure = erasure

    def execute(self, tenant_id: UUID) -> ClosureSummary:
        return self._erasure.closure_summary(_business(self._erasure, tenant_id))


class RequestAccountClosure:
    """Typing the business name confirms it. The business stops at once (suspended: no
    replies, emails or checks) and a job deletes everything shortly after."""

    def __init__(
        self, erasure: SqlAlchemyErasure, queue: JobQueue, audit: AuditLog, clock: Clock
    ) -> None:
        self._erasure = erasure
        self._queue = queue
        self._audit = audit
        self._clock = clock

    def execute(self, admin_id: UUID, tenant_id: UUID, typed_name: str) -> ClosureSummary:
        business = _business(self._erasure, tenant_id)
        if business.is_platform:
            raise PlatformBusinessError(str(tenant_id))
        if typed_name.strip().casefold() != business.name.strip().casefold():
            raise ConfirmationMismatchError(str(tenant_id))
        now = self._clock()
        self._erasure.mark_closing(tenant_id, now)
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.ADMIN,
                InmoAction.ACCOUNT_CLOSURE_REQUESTED,
                actor_profile_id=admin_id,
            )
        )
        self._queue.enqueue(
            NewJob(
                CLOSE_ACCOUNT_JOB,
                {"tenant_id": str(tenant_id), "admin_id": str(admin_id)},
                dedupe_key=f"tenant-close:{tenant_id}",
            )
        )
        return self.summary(tenant_id)

    def summary(self, tenant_id: UUID) -> ClosureSummary:
        return self._erasure.closure_summary(_business(self._erasure, tenant_id))


class CloseAccount:
    """The closing job. Idempotent: a retry finds less to delete, and a closed business is
    left alone.

    1. Unsubscribe our app from the business's WABA (nothing else at Meta changes; a failure
       is logged and does not stop the deletion: the token may already be revoked).
    2. Delete every row of the business (`SqlAlchemyErasure.delete_tenant`).
    3. Delete the auth provider's user of each person who belongs to no other business.
    4. Turn the `tenants` row into a tombstone and record one audit event, counts only.
    """

    def __init__(
        self,
        erasure: SqlAlchemyErasure,
        connections: ConnectionRepository,
        graph_for: Callable[[WhatsAppConnection], GraphPort],
        directory: AccountDirectory,
        audit: AuditLog,
        queue: JobQueue,
        clock: Clock,
    ) -> None:
        self._erasure = erasure
        self._queue = queue
        self._connections = connections
        self._graph_for = graph_for
        self._directory = directory
        self._audit = audit
        self._clock = clock

    def __call__(self, job: Job) -> None:
        tenant_id = UUID(job.payload["tenant_id"])
        if self._erasure.business(tenant_id) is None:
            return  # already closed (or never existed)
        meta = self._unsubscribe(tenant_id)
        erasure = self._erasure.delete_tenant(tenant_id, keep_job_id=job.id)
        for user in erasure.users:
            if not user.keep_login:
                self._directory.delete_user(user.user_id, user.email)
        self._erasure.tombstone(tenant_id)
        admin_id = job.payload.get("admin_id")
        self._audit.record(
            AuditEvent(
                tenant_id,
                self._clock(),
                ActorKind.ADMIN if admin_id else ActorKind.SYSTEM,
                InmoAction.ACCOUNT_CLOSED,
                {
                    **_counts(erasure.counts),
                    "properties": erasure.properties,
                    "users": len(erasure.users),
                    "users_kept": sum(1 for user in erasure.users if user.keep_login),
                    "code": meta,
                },
                actor_profile_id=UUID(admin_id) if admin_id else None,
            )
        )
        self._queue.enqueue(
            NewJob(
                CLOSE_CLEANUP_JOB,
                {"job_id": str(job.id)},
                run_at=self._clock() + CLEANUP_RETRY,
                dedupe_key=f"tenant-close-cleanup:{job.id}",
            )
        )
        logger.info("account_closed", extra={"tenant_id": str(tenant_id)})

    def _unsubscribe(self, tenant_id: UUID) -> str:
        connection = self._connections.get_by_tenant(tenant_id)
        if connection is None:
            return "no_whatsapp"
        try:
            self._graph_for(connection).unsubscribe_app(connection)
        except Exception as error:  # a revoked token, Meta down: the data goes anyway
            logger.warning(
                "account_close_unsubscribe_failed",
                extra={"tenant_id": str(tenant_id), "error": type(error).__name__},
            )
            return "meta_unsubscribe_failed"
        return "meta_unsubscribed"


class ForgetClosingJob:
    """The cleanup job: once the closing job is done, its row goes too."""

    def __init__(self, erasure: SqlAlchemyErasure, clock: Clock) -> None:
        self._erasure = erasure
        self._clock = clock

    def __call__(self, job: Job) -> Reschedule | None:
        if self._erasure.forget_finished_job(UUID(job.payload["job_id"])) is None:
            return Reschedule(self._clock() + CLEANUP_RETRY)
        return None
