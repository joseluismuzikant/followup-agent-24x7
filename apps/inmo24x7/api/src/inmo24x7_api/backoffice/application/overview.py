"""S8 Negocios and S9 Detalle del negocio, for platform admins."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from followup_core.messaging.domain.connection import WhatsAppConnection
from followup_core.messaging.domain.signup import Signup
from followup_core.tenancy.domain.business_settings import DEFAULT_TIMEZONE
from followup_core.tenancy.domain.errors import TenantNotFoundError
from followup_core.tenancy.domain.plans import MONTHLY_CONVERSATIONS
from followup_core.tenancy.domain.tenant import Tenant

from ..domain.rules import Kpis, TenantFilter, TenantRow, kpis, matches
from ..infrastructure.queries import ActivityRow, SqlAlchemyBackofficeQueries, UserRow

PAGE_SIZE = 20


@dataclass(frozen=True, slots=True)
class TenantList:
    items: Sequence[TenantRow]
    total: int
    page: int
    kpis: Kpis


@dataclass(frozen=True, slots=True)
class TenantDetail:
    row: TenantRow
    tenant: Tenant
    connection: WhatsAppConnection | None
    signup: Signup | None
    users: Sequence[UserRow]
    activity: Sequence[ActivityRow]
    conversations_this_month: int
    allowance: int


def month_start(now: datetime, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    local = now.astimezone(ZoneInfo(timezone))
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class ListBusinesses:
    def __init__(self, queries: SqlAlchemyBackofficeQueries, clock: Callable[[], datetime]):
        self._queries = queries
        self._clock = clock

    def execute(self, wanted: TenantFilter, query: str, page: int) -> TenantList:
        """Every business is read once (MVP scale: hundreds); the KPIs cover them all and
        the filter and search use the same rules."""
        now = self._clock()
        rows = self._queries.tenants(now)
        found = [row for row in rows if matches(row, wanted, query, now)]
        start = (page - 1) * PAGE_SIZE
        return TenantList(found[start : start + PAGE_SIZE], len(found), page, kpis(rows))


class GetBusiness:
    def __init__(
        self,
        queries: SqlAlchemyBackofficeQueries,
        tenant: Callable[[UUID], Tenant | None],
        connection: Callable[[UUID], WhatsAppConnection | None],
        signup: Callable[[UUID], Signup | None],
        clock: Callable[[], datetime],
    ) -> None:
        self._queries = queries
        self._tenant = tenant
        self._connection = connection
        self._signup = signup
        self._clock = clock

    def execute(self, tenant_id: UUID) -> TenantDetail:
        now = self._clock()
        rows = self._queries.tenants(now, tenant_id)
        tenant = self._tenant(tenant_id)
        if not rows or tenant is None:
            raise TenantNotFoundError(str(tenant_id))
        return TenantDetail(
            row=rows[0],
            tenant=tenant,
            connection=self._connection(tenant_id),
            signup=self._signup(tenant_id),
            users=self._queries.users(tenant_id),
            activity=self._queries.activity(tenant_id),
            conversations_this_month=self._queries.conversations_since(tenant_id, month_start(now)),
            allowance=MONTHLY_CONVERSATIONS,
        )
