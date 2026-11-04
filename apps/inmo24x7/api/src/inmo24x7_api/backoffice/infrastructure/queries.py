"""The backoffice's read models, in SQL across contexts (like the dashboard's). One row per
business; the rules in domain/rules.py decide badges, KPIs and filters on top of it."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..domain.rules import Onboarding, TenantRow

_TENANTS = text(
    """
    SELECT t.id, t.name, t.status, t.plan, t.trial_ends_at, t.created_at,
           (SELECT min(p.email) FROM profiles p
             WHERE p.tenant_id = t.id AND p.role = 'owner') AS owner_email,
           (SELECT min(c.email) FROM tenant_owner_claims c
             WHERE c.tenant_id = t.id AND c.claimed_at IS NULL) AS claim_email,
           o.finished_at IS NOT NULL AS finished,
           EXISTS (SELECT 1 FROM agent_config_versions v WHERE v.tenant_id = t.id)
             AS agent_configured,
           EXISTS (
             SELECT 1 FROM conversation_messages m
             JOIN conversation_threads th ON th.id = m.thread_id
             JOIN profiles sp ON sp.id = th.started_by_profile_id
             WHERE th.tenant_id = t.id AND th.channel = 'simulator'
               AND sp.tenant_id = t.id AND m.direction = 'inbound'
           ) AS agent_tested,
           EXISTS (SELECT 1 FROM properties pr WHERE pr.tenant_id = t.id) AS own_properties,
           w.status AS whatsapp_status,
           w.business_verification,
           (SELECT count(*) FROM leads l
             WHERE l.tenant_id = t.id AND NOT l.is_test AND l.created_at >= :since)
             AS leads_7d
    FROM tenants t
    LEFT JOIN tenant_onboarding o ON o.tenant_id = t.id
    LEFT JOIN whatsapp_connections w ON w.tenant_id = t.id
    WHERE NOT EXISTS (
      SELECT 1 FROM profiles a WHERE a.tenant_id = t.id AND a.is_platform_admin
    )
      AND (CAST(:tenant_id AS uuid) IS NULL OR t.id = CAST(:tenant_id AS uuid))
    ORDER BY t.created_at DESC, t.id
    """
)


def _row(row: Any) -> TenantRow:
    return TenantRow(
        id=row.id,
        name=row.name,
        suspended=row.status == "suspended",
        plan=row.plan,
        trial_ends_at=row.trial_ends_at,
        created_at=row.created_at,
        owner_email=row.owner_email or row.claim_email,
        owner_pending=row.owner_email is None and row.claim_email is not None,
        onboarding=Onboarding(
            agent_configured=row.agent_configured,
            agent_tested=row.agent_tested,
            whatsapp_connected=row.whatsapp_status == "connected",
            own_properties=row.own_properties,
            finished=row.finished,
        ),
        whatsapp_status=row.whatsapp_status,
        business_verification=row.business_verification,
        leads_last_7_days=row.leads_7d,
    )


@dataclass(frozen=True, slots=True)
class UserRow:
    id: UUID
    name: str
    email: str
    role: str


@dataclass(frozen=True, slots=True)
class ActivityRow:
    at: datetime
    actor_kind: str
    actor_name: str | None
    action: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class JobCount:
    kind: str
    status: str
    count: int


@dataclass(frozen=True, slots=True)
class SystemNumbers:
    jobs: Sequence[JobCount]
    dead_last_24h: int
    oldest_queued_seconds: float | None
    webhooks_last_hour: int
    signature_rejections_last_24h: int
    failed_sends_by_code: Sequence[tuple[str, int]]
    database_ok: bool


class SqlAlchemyBackofficeQueries:
    def __init__(self, session: Session) -> None:
        self._session = session

    def tenants(self, now: datetime, tenant_id: UUID | None = None) -> Sequence[TenantRow]:
        rows = self._session.execute(
            _TENANTS,
            {"since": now - timedelta(days=7), "tenant_id": str(tenant_id) if tenant_id else None},
        )
        return [_row(row) for row in rows]

    def users(self, tenant_id: UUID) -> Sequence[UserRow]:
        rows = self._session.execute(
            text(
                "SELECT id, display_name, email, role FROM profiles WHERE tenant_id = :t "
                "ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'manager' THEN 1 "
                "WHEN 'agent' THEN 2 ELSE 3 END, email"
            ),
            {"t": tenant_id},
        )
        return [
            UserRow(row.id, (row.display_name or "").strip() or row.email, row.email, row.role)
            for row in rows
        ]

    def activity(self, tenant_id: UUID, limit: int = 20) -> Sequence[ActivityRow]:
        rows = self._session.execute(
            text(
                """
                SELECT e.at, e.actor_kind, e.action, e.details,
                       COALESCE(NULLIF(trim(p.display_name), ''), p.email) AS actor_name
                FROM audit_events e
                LEFT JOIN profiles p ON p.id = e.actor_profile_id
                WHERE e.tenant_id = :t
                ORDER BY e.at DESC, e.id
                LIMIT :limit
                """
            ),
            {"t": tenant_id, "limit": limit},
        )
        return [
            ActivityRow(row.at, row.actor_kind, row.actor_name, row.action, dict(row.details))
            for row in rows
        ]

    def conversations_since(self, tenant_id: UUID, since: datetime) -> int:
        """Threads with at least one inbound message since `since` on a real channel."""
        return int(
            self._session.scalar(
                text(
                    """
                    SELECT count(DISTINCT t.id) FROM conversation_threads t
                    JOIN conversation_messages m ON m.thread_id = t.id
                    WHERE t.tenant_id = :t AND t.channel = 'whatsapp'
                      AND m.direction = 'inbound' AND m.created_at >= :since
                    """
                ),
                {"t": tenant_id, "since": since},
            )
            or 0
        )

    def plan_counts(self) -> dict[str, int]:
        rows = self._session.execute(
            text(
                """
                SELECT t.plan, count(*) AS n FROM tenants t
                WHERE NOT EXISTS (
                  SELECT 1 FROM profiles a WHERE a.tenant_id = t.id AND a.is_platform_admin
                )
                GROUP BY t.plan
                """
            )
        )
        return {row.plan: row.n for row in rows}

    def system(self, now: datetime) -> SystemNumbers:
        day_ago = now - timedelta(hours=24)
        try:
            self._session.execute(text("SELECT 1"))
            database_ok = True
        except Exception:  # noqa: BLE001 - reported, not raised
            self._session.rollback()
            database_ok = False
        jobs = [
            JobCount(row.kind, row.status, row.n)
            for row in self._session.execute(
                text(
                    """
                    SELECT kind, status, count(*) AS n FROM jobs
                    WHERE status IN ('queued', 'running', 'failed')
                       OR (status = 'dead' AND coalesce(finished_at, created_at) >= :since)
                    GROUP BY kind, status ORDER BY kind, status
                    """
                ),
                {"since": day_ago},
            )
        ]
        oldest = self._session.scalar(
            text("SELECT min(run_at) FROM jobs WHERE status = 'queued' AND run_at <= :now"),
            {"now": now},
        )
        failed = [
            (row.code, row.n)
            for row in self._session.execute(
                text(
                    """
                    SELECT coalesce(error_code, 'unknown') AS code, count(*) AS n
                    FROM whatsapp_outbound
                    WHERE status = 'failed' AND updated_at >= :since
                    GROUP BY 1 ORDER BY 2 DESC, 1
                    """
                ),
                {"since": day_ago},
            )
        ]

        def counted(kind: str, since: datetime) -> int:
            return int(
                self._session.scalar(
                    text(
                        "SELECT coalesce(sum(count), 0) FROM webhook_counters "
                        "WHERE kind = :kind AND hour >= :since"
                    ),
                    {"kind": kind, "since": since.replace(minute=0, second=0, microsecond=0)},
                )
                or 0
            )

        return SystemNumbers(
            jobs=jobs,
            dead_last_24h=sum(job.count for job in jobs if job.status == "dead"),
            oldest_queued_seconds=(now - oldest).total_seconds() if oldest else None,
            webhooks_last_hour=counted("received", now - timedelta(hours=1)),
            signature_rejections_last_24h=counted("signature_rejected", day_ago),
            failed_sends_by_code=failed,
            database_ok=database_ok,
        )


def utc_now() -> datetime:
    return datetime.now(UTC)
