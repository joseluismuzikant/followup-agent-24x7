"""The Cuentas Claras backoffice's read model: one row per Cuentas Claras business (never
another product's), with its owner, plan, onboarding, clients and what it has to collect.
Platform admins' own tenants are left out."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...product import PRODUCT

_BUSINESSES = text(
    """
    SELECT t.id, t.name, t.status, t.plan, t.trial_ends_at, t.created_at, t.suspended_reason,
           (SELECT min(p.email) FROM profiles p
             WHERE p.tenant_id = t.id AND p.role = 'owner') AS owner_email,
           (SELECT min(c.email) FROM tenant_owner_claims c
             WHERE c.tenant_id = t.id AND c.claimed_at IS NULL) AS claim_email,
           EXISTS (SELECT 1 FROM cc_invoices i WHERE i.tenant_id = t.id) AS invoices_loaded,
           (SELECT count(*) FROM cc_clients c WHERE c.tenant_id = t.id) AS clients,
           (SELECT coalesce(sum(i.amount), 0) FROM cc_invoices i
             WHERE i.tenant_id = t.id AND i.status IN ('open', 'promised')
               AND i.currency = 'ARS') AS open_amount
    FROM tenants t
    WHERE t.product = :product
      AND NOT EXISTS (
        SELECT 1 FROM profiles a WHERE a.tenant_id = t.id AND a.is_platform_admin
      )
      AND (CAST(:tenant_id AS uuid) IS NULL OR t.id = CAST(:tenant_id AS uuid))
      AND (:q = '' OR lower(t.name) LIKE :pattern OR EXISTS (
        SELECT 1 FROM profiles o WHERE o.tenant_id = t.id AND lower(o.email) LIKE :pattern
      ))
    ORDER BY t.created_at DESC, t.id
    """
)


@dataclass(frozen=True, slots=True)
class BusinessRow:
    id: UUID
    name: str
    suspended: bool
    suspended_reason: str | None
    plan: str
    trial_ends_at: datetime
    created_at: datetime
    owner_email: str | None
    owner_pending: bool
    invoices_loaded: bool
    clients: int
    open_amount: Decimal


@dataclass(frozen=True, slots=True)
class ActivityRow:
    at: datetime
    actor_kind: str
    actor_name: str | None
    action: str
    details: dict[str, Any]


def _row(row: Any) -> BusinessRow:
    return BusinessRow(
        id=row.id,
        name=row.name,
        suspended=row.status == "suspended",
        suspended_reason=row.suspended_reason,
        plan=row.plan,
        trial_ends_at=row.trial_ends_at,
        created_at=row.created_at,
        owner_email=row.owner_email or row.claim_email,
        owner_pending=row.owner_email is None and row.claim_email is not None,
        invoices_loaded=bool(row.invoices_loaded),
        clients=int(row.clients),
        open_amount=Decimal(row.open_amount),
    )


class SqlAlchemyCuentasBackofficeQueries:
    def __init__(self, session: Session) -> None:
        self._session = session

    def businesses(self, q: str = "", tenant_id: UUID | None = None) -> Sequence[BusinessRow]:
        query = q.strip().lower()
        rows = self._session.execute(
            _BUSINESSES,
            {
                "product": PRODUCT.value,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "q": query,
                "pattern": f"%{query}%",
            },
        )
        return [_row(row) for row in rows]

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
