"""The deletes behind "Eliminar datos de un contacto" and "Cerrar cuenta y eliminar datos".

Plain SQL on purpose: every table is named here, in foreign-key order, so a reviewer can
check what goes and what stays. Everything runs in the caller's transaction.

Kept on purpose:
- `do_not_contact` survives a contact's deletion (its message references are cleared), so a
  "BAJA" keeps being honored;
- `llm_usage` rows stay for the cost totals, unlinked from the deleted thread;
- `audit_events` stay without the deleted lead's id (they never hold personal data);
- a closed business keeps its `tenants` row as a tombstone (see `tombstone`).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from followup_core.conversation.domain.answers import normalize
from sqlalchemy import CursorResult, bindparam, text
from sqlalchemy.orm import Session

from ..product import PRODUCT
from .domain import (
    CLOSING_REASON,
    TOMBSTONE_NAME,
    ClosureSummary,
    ContactSummary,
    ErasedCounts,
    ProfileUser,
    TenantErasure,
    wa_id_variants,
)

MAX_CONTACTS = 20


@dataclass(frozen=True, slots=True)
class BusinessRow:
    id: UUID
    name: str
    status: str
    suspended_reason: str | None
    is_platform: bool


@dataclass(frozen=True, slots=True)
class _Scope:
    thread_ids: list[UUID]
    thread_keys: list[str]
    lead_ids: list[UUID]
    message_ids: list[UUID]
    event_ids: list[UUID]
    wamids: list[str]


def _rowcount(result: Any) -> int:
    """How many rows a DELETE or UPDATE touched (Session.execute is typed as a plain Result)."""
    return cast(CursorResult[Any], result).rowcount


def _strings(values: Sequence[Any]) -> list[str]:
    return [str(value) for value in values]


_CONTACTS = text(
    """
    SELECT th.visitor_id AS wa_id,
           max(coalesce(th.last_message_at, th.created_at)) AS last_activity_at,
           count(DISTINCT l.id) AS leads,
           array_remove(array_agg(DISTINCT l.visitor_name), NULL) AS names,
           (SELECT count(*) FROM conversation_messages m
             JOIN conversation_threads t2 ON t2.id = m.thread_id
             WHERE t2.tenant_id = th.tenant_id AND t2.channel = 'whatsapp'
               AND t2.visitor_id = th.visitor_id) AS messages,
           (SELECT count(*) FROM visits v
             JOIN leads l2 ON l2.id = v.lead_id
             JOIN conversation_threads t3 ON t3.id = l2.thread_id
             WHERE t3.tenant_id = th.tenant_id AND t3.channel = 'whatsapp'
               AND t3.visitor_id = th.visitor_id) AS visits,
           EXISTS (SELECT 1 FROM do_not_contact d
                    WHERE d.tenant_id = th.tenant_id AND d.wa_id = th.visitor_id)
             AS do_not_contact
    FROM conversation_threads th
    LEFT JOIN leads l ON l.thread_id = th.id
    WHERE th.tenant_id = :tenant_id AND th.channel = 'whatsapp'
      AND (th.visitor_id = ANY(CAST(:wa_ids AS text[]))
           OR (CAST(:digits AS text) IS NOT NULL AND th.visitor_id LIKE :digits)
           OR (CAST(:words AS text) IS NOT NULL AND l.search_text LIKE :words))
    GROUP BY th.tenant_id, th.visitor_id
    ORDER BY last_activity_at DESC NULLS LAST
    LIMIT :limit
    """
)

_JOBS = text(
    """
    DELETE FROM jobs
    WHERE (CAST(:keep AS uuid) IS NULL OR id <> CAST(:keep AS uuid))
      AND (payload->>'event_id' = ANY(CAST(:event_ids AS text[]))
           OR payload->>'lead_id' = ANY(CAST(:lead_ids AS text[]))
           OR payload->>'wamid' = ANY(CAST(:wamids AS text[]))
           OR (jsonb_typeof(payload->'message_ids') = 'array'
               AND payload->'message_ids' ?| CAST(:message_ids AS text[]))
           OR payload->>'invitation_id' = ANY(CAST(:invitation_ids AS text[]))
           OR (CAST(:tenant_id AS text) IS NOT NULL
               AND payload->>'tenant_id' = CAST(:tenant_id AS text)))
    """
)


class SqlAlchemyErasure:
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- reading ------------------------------------------------------------------------

    def business(self, tenant_id: UUID) -> BusinessRow | None:
        row = self._session.execute(
            text(
                """
                SELECT t.id, t.name, t.status, t.suspended_reason,
                       EXISTS (SELECT 1 FROM profiles p
                                WHERE p.tenant_id = t.id AND p.is_platform_admin) AS is_platform
                FROM tenants t
                WHERE t.id = :tenant_id AND t.product = :product AND t.status <> 'deleted'
                """
            ),
            {"tenant_id": tenant_id, "product": str(PRODUCT)},
        ).one_or_none()
        if row is None:
            return None
        return BusinessRow(row.id, row.name, row.status, row.suspended_reason, row.is_platform)

    def contacts(
        self, tenant_id: UUID, *, wa_ids: Sequence[str] = (), digits: str = "", words: str = ""
    ) -> list[ContactSummary]:
        rows = self._session.execute(
            _CONTACTS,
            {
                "tenant_id": tenant_id,
                "wa_ids": list(wa_ids),
                "digits": f"%{digits}%" if digits else None,
                "words": f"%{normalize(words)}%" if words else None,
                "limit": MAX_CONTACTS,
            },
        )
        return [
            ContactSummary(
                wa_id=row.wa_id,
                names=tuple(sorted(row.names or ())),
                leads=row.leads,
                messages=row.messages,
                visits=row.visits,
                last_activity_at=row.last_activity_at,
                do_not_contact=row.do_not_contact,
            )
            for row in rows
        ]

    def closure_summary(self, business: BusinessRow) -> ClosureSummary:
        row = self._session.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM properties WHERE tenant_id = :t) AS properties,
                  (SELECT count(*) FROM leads WHERE tenant_id = :t) AS leads,
                  (SELECT count(*) FROM conversation_threads WHERE tenant_id = :t)
                    AS conversations,
                  (SELECT count(*) FROM conversation_messages m
                     JOIN conversation_threads th ON th.id = m.thread_id
                     WHERE th.tenant_id = :t) AS messages,
                  (SELECT count(*) FROM profiles WHERE tenant_id = :t) AS users,
                  (SELECT count(*) FROM profiles p
                     WHERE p.tenant_id = :t AND EXISTS (
                       SELECT 1 FROM profiles o
                        WHERE o.user_id = p.user_id AND o.id <> p.id)) AS users_kept,
                  EXISTS (SELECT 1 FROM whatsapp_connections
                           WHERE tenant_id = :t AND status <> 'disconnected') AS whatsapp
                """
            ),
            {"t": business.id},
        ).one()
        return ClosureSummary(
            name=business.name,
            properties=row.properties,
            leads=row.leads,
            conversations=row.conversations,
            messages=row.messages,
            users=row.users,
            users_kept=row.users_kept,
            whatsapp_connected=row.whatsapp,
            closing=business.status == "suspended" and business.suspended_reason == CLOSING_REASON,
        )

    # --- one contact --------------------------------------------------------------------

    def delete_contact(self, tenant_id: UUID, wa_id: str) -> ErasedCounts:
        """Everything of that WhatsApp contact in that business; the do-not-contact flag
        stays (without its message references)."""
        variants = wa_id_variants(wa_id)
        threads = self._session.execute(
            text(
                "SELECT id, key FROM conversation_threads "
                "WHERE tenant_id = :t AND channel = 'whatsapp' AND visitor_id = ANY(:w)"
            ),
            {"t": tenant_id, "w": variants},
        ).all()
        scope = self._scope(
            tenant_id,
            [row.id for row in threads],
            [row.key for row in threads],
            events_where="tenant_id = :t AND wa_id = ANY(:w)",
            events_params={"t": tenant_id, "w": variants},
        )
        counts = self._erase(scope, tenant_id=None)
        # The audit log keeps the events, without the deleted lead's id.
        self._run(
            "UPDATE audit_events SET details = details - 'lead_id' "
            "WHERE tenant_id = :t AND details->>'lead_id' = ANY(:ids)",
            t=tenant_id,
            ids=_strings(scope.lead_ids),
        )
        self._run(
            "UPDATE do_not_contact SET source_message_id = NULL, confirmation_message_id = NULL "
            "WHERE tenant_id = :t AND wa_id = ANY(:w)",
            t=tenant_id,
            w=variants,
        )
        return counts

    # --- a whole business ---------------------------------------------------------------

    def delete_tenant(self, tenant_id: UUID, keep_job_id: UUID | None) -> TenantErasure:
        """Every row of the business except its `tenants` row and its `llm_usage` rows
        (unlinked). The caller deletes the auth provider's users, turns the tenant into a
        tombstone (`tombstone`) and records the closing audit event afterwards."""
        thread_rows = self._session.execute(
            text("SELECT id, key FROM conversation_threads WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).all()
        scope = self._scope(
            tenant_id,
            [row.id for row in thread_rows],
            [row.key for row in thread_rows],
            events_where="tenant_id = :t",
            events_params={"t": tenant_id},
            all_leads=True,
        )
        invitation_ids = _strings(
            self._session.scalars(
                text("SELECT id FROM invitations WHERE tenant_id = :t"), {"t": tenant_id}
            ).all()
        )
        counts = self._erase(
            scope, tenant_id=tenant_id, keep_job_id=keep_job_id, invitation_ids=invitation_ids
        )
        users = tuple(
            ProfileUser(row.user_id, row.email, row.keep_login)
            for row in self._session.execute(
                text(
                    """
                    SELECT p.user_id, p.email,
                           EXISTS (SELECT 1 FROM profiles o
                                    WHERE o.user_id = p.user_id AND o.id <> p.id) AS keep_login
                    FROM profiles p WHERE p.tenant_id = :t
                    """
                ),
                {"t": tenant_id},
            )
        )
        properties = self._run("DELETE FROM properties WHERE tenant_id = :t", t=tenant_id)
        for table in (
            "property_imports",
            "inmo_condition_settings",
            "whatsapp_connections",
            "whatsapp_signups",
            "do_not_contact",
            "agent_config_versions",
            "tenant_settings",
            "tenant_onboarding",
            "tenant_owner_claims",
            "invitations",
            "audit_events",
            "profiles",
        ):
            self._run(f"DELETE FROM {table} WHERE tenant_id = :t", t=tenant_id)  # noqa: S608
        # A login nobody else uses goes with the business (the auth provider's user is the
        # caller's job: it is not in this database).
        gone = [user.user_id for user in users if not user.keep_login]
        if gone:
            self._in("DELETE FROM accounts WHERE user_id IN :ids", gone)
        return TenantErasure(counts=counts, properties=properties, users=users)

    def tombstone(self, tenant_id: UUID) -> None:
        """The `tenants` row stays because `llm_usage` (cost history per business and month)
        and the closing audit event reference it; it keeps no name or personal data."""
        self._run(
            """
            UPDATE tenants
               SET name = :name, slug = :slug, status = 'deleted',
                   suspended_reason = NULL, suspended_at = NULL
             WHERE id = :t
            """,
            t=tenant_id,
            name=TOMBSTONE_NAME,
            slug=f"eliminada-{tenant_id.hex}",
        )

    def forget_finished_job(self, job_id: UUID) -> bool | None:
        """Deletes a finished job's row. None while it is still running (try later)."""
        status = self._session.scalar(
            text("SELECT status FROM jobs WHERE id = :id"), {"id": job_id}
        )
        if status is None:
            return False
        if status in ("queued", "running"):
            return None
        self._run("DELETE FROM jobs WHERE id = :id", id=job_id)
        return True

    def mark_closing(self, tenant_id: UUID, at: Any) -> None:
        self._run(
            "UPDATE tenants SET status = 'suspended', suspended_reason = :reason, "
            "suspended_at = :at WHERE id = :t",
            t=tenant_id,
            reason=CLOSING_REASON,
            at=at,
        )

    # --- shared -------------------------------------------------------------------------

    def _scope(
        self,
        tenant_id: UUID,
        thread_ids: list[UUID],
        thread_keys: list[str],
        *,
        events_where: str,
        events_params: dict[str, Any],
        all_leads: bool = False,
    ) -> _Scope:
        if all_leads:
            lead_ids = list(
                self._session.scalars(
                    text("SELECT id FROM leads WHERE tenant_id = :t"), {"t": tenant_id}
                )
            )
        else:
            lead_ids = self._ids("SELECT id FROM leads WHERE thread_id IN :ids", thread_ids)
        message_ids = self._ids(
            "SELECT id FROM conversation_messages WHERE thread_id IN :ids", thread_ids
        )
        events = self._session.execute(
            text(f"SELECT id, wamid FROM whatsapp_inbound_events WHERE {events_where}"),  # noqa: S608
            events_params,
        ).all()
        outbound_wamids = self._ids(
            "SELECT wamid FROM whatsapp_outbound WHERE wamid IS NOT NULL AND message_id IN :ids",
            message_ids,
        )
        return _Scope(
            thread_ids=thread_ids,
            thread_keys=thread_keys,
            lead_ids=lead_ids,
            message_ids=message_ids,
            event_ids=[row.id for row in events],
            wamids=[row.wamid for row in events] + [str(item) for item in outbound_wamids],
        )

    def _erase(
        self,
        scope: _Scope,
        *,
        tenant_id: UUID | None,
        keep_job_id: UUID | None = None,
        invitation_ids: Sequence[str] = (),
    ) -> ErasedCounts:
        jobs = _rowcount(
            self._session.execute(
                _JOBS,
                {
                    "keep": keep_job_id,
                    "event_ids": _strings(scope.event_ids),
                    "lead_ids": _strings(scope.lead_ids),
                    "wamids": list(scope.wamids),
                    "message_ids": _strings(scope.message_ids),
                    "invitation_ids": list(invitation_ids),
                    "tenant_id": str(tenant_id) if tenant_id else None,
                },
            )
        )
        leads = scope.lead_ids
        for table in ("lead_status_changes", "lead_condition_events", "lead_property_matches"):
            self._in(f"DELETE FROM {table} WHERE lead_id IN :ids", leads)  # noqa: S608
        visits = self._in("DELETE FROM visits WHERE lead_id IN :ids", leads)
        lead_count = self._in("DELETE FROM leads WHERE id IN :ids", leads)
        outbound = self._in(
            "DELETE FROM whatsapp_outbound WHERE message_id IN :ids", scope.message_ids
        )
        unlinked = self._in(
            "UPDATE llm_usage SET thread_id = NULL WHERE thread_id IN :ids", scope.thread_ids
        )
        messages = self._in(
            "DELETE FROM conversation_messages WHERE thread_id IN :ids", scope.thread_ids
        )
        threads = self._in("DELETE FROM conversation_threads WHERE id IN :ids", scope.thread_ids)
        checkpoints = 0
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            deleted = self._in(f"DELETE FROM {table} WHERE thread_id IN :ids", scope.thread_keys)  # noqa: S608
            if table == "checkpoints":
                checkpoints = deleted
        events = self._in("DELETE FROM whatsapp_inbound_events WHERE id IN :ids", scope.event_ids)
        return ErasedCounts(
            leads=lead_count,
            threads=threads,
            messages=messages,
            visits=visits,
            inbound_events=events,
            outbound_parts=outbound,
            jobs=jobs,
            checkpoints=checkpoints,
            llm_calls_unlinked=unlinked,
        )

    def _ids(self, sql: str, ids: Sequence[Any]) -> list[Any]:
        if not ids:
            return []
        statement = text(sql).bindparams(bindparam("ids", expanding=True))
        return list(self._session.scalars(statement, {"ids": list(ids)}))

    def _in(self, sql: str, ids: Sequence[Any]) -> int:
        if not ids:
            return 0
        statement = text(sql).bindparams(bindparam("ids", expanding=True))
        return _rowcount(self._session.execute(statement, {"ids": list(ids)}))

    def _run(self, sql: str, **params: Any) -> int:
        return _rowcount(self._session.execute(text(sql), params))
