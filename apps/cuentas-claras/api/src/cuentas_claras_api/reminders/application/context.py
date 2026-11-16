"""Everything about one business that planning, sending and "Lo próximo" read: its policy
(the default until the owner saves one), its sending calendar, its WhatsApp connection
and the templates it can send."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from uuid import UUID

from followup_core.messaging.application.health import stops_sending
from followup_core.messaging.domain.connection import ConnectionStatus, WhatsAppConnection
from followup_core.messaging.domain.repositories import ConnectionRepository
from followup_core.tenancy.domain.business_settings import ScheduleBlock

from ..domain.calendar import SendingCalendar
from ..domain.next_action import Connection
from ..domain.policy import ReminderPolicy, TemplateKind
from ..domain.repositories import PolicyRepository, TemplateRepository
from ..domain.templates import WhatsAppTemplate, in_use

Clock = Callable[[], datetime]
# (timezone, team hours) from Configuración.
ScheduleOf = Callable[[UUID], tuple[str, tuple[ScheduleBlock, ...]]]
Holidays = Callable[[Iterable[int]], frozenset[date]]


def utc_now() -> datetime:
    return datetime.now(UTC)


def connection_state(connection: WhatsAppConnection | None) -> Connection:
    if connection is None or connection.status is ConnectionStatus.DISCONNECTED:
        return Connection.NONE
    if connection.is_failing and stops_sending(connection.last_error_code or ""):
        return Connection.ERROR
    return Connection.OK


@dataclass(frozen=True)
class ReminderContext:
    tenant_id: UUID
    business_name: str
    policy: ReminderPolicy
    calendar: SendingCalendar
    whatsapp: WhatsAppConnection | None
    versions: list[WhatsAppTemplate] = field(default_factory=list)

    @property
    def connection(self) -> Connection:
        return connection_state(self.whatsapp)

    def template(self, kind: TemplateKind) -> WhatsAppTemplate | None:
        """The version reminders of this kind send (the newest approved one)."""
        return in_use([item for item in self.versions if item.kind is kind])

    @property
    def approved(self) -> set[TemplateKind]:
        return {kind for kind in TemplateKind if self.template(kind) is not None}


class LoadContext:
    def __init__(
        self,
        policies: PolicyRepository,
        templates: TemplateRepository,
        schedule_of: ScheduleOf,
        holidays: Holidays,
        connections: ConnectionRepository,
        business_name: Callable[[UUID], str],
        clock: Clock = utc_now,
    ) -> None:
        self._policies = policies
        self._templates = templates
        self._schedule_of = schedule_of
        self._holidays = holidays
        self._connections = connections
        self._business_name = business_name
        self._clock = clock

    def __call__(self, tenant_id: UUID) -> ReminderContext:
        policy = self._policies.get(tenant_id) or ReminderPolicy.default(tenant_id)
        timezone, team_hours = self._schedule_of(tenant_id)
        year = self._clock().year
        days = self._holidays([year - 1, year, year + 1]) if policy.skip_holidays else frozenset()
        return ReminderContext(
            tenant_id=tenant_id,
            business_name=self._business_name(tenant_id),
            policy=policy,
            calendar=SendingCalendar(timezone, policy.window, team_hours, days),
            whatsapp=self._connections.get_by_tenant(tenant_id),
            versions=self._templates.for_tenant(tenant_id),
        )
