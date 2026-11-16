from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog

from ...audit import CuentasAction
from ..domain.client import Client, ClientFields
from ..domain.errors import ClientNotFoundError, CuitTakenError
from ..domain.repository import ClientBalance, ClientPage, ClientRepository

Clock = Callable[[], datetime]
PAGE_SIZE = 25


def utc_now() -> datetime:
    return datetime.now(UTC)


class CreateClient:
    def __init__(self, clients: ClientRepository, audit: AuditLog, clock: Clock = utc_now) -> None:
        self._clients = clients
        self._audit = audit
        self._clock = clock

    def execute(self, tenant_id: UUID, profile_id: UUID, fields: ClientFields) -> Client:
        now = self._clock()
        client = Client.create(tenant_id, fields, now)
        if client.cuit and self._clients.find_by_cuit(tenant_id, client.cuit) is not None:
            raise CuitTakenError(client.cuit)
        self._clients.add(client)
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.USER,
                CuentasAction.CLIENT_CREATED,
                {"client_id": str(client.id)},
                actor_profile_id=profile_id,
            )
        )
        return client


class UpdateClient:
    def __init__(self, clients: ClientRepository, audit: AuditLog, clock: Clock = utc_now) -> None:
        self._clients = clients
        self._audit = audit
        self._clock = clock

    def execute(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        client_id: UUID,
        fields: ClientFields,
        active: bool | None = None,
        no_reminders: bool | None = None,
    ) -> Client:
        current = self._clients.get(tenant_id, client_id)
        if current is None:
            raise ClientNotFoundError(str(client_id))
        now = self._clock()
        updated = current.with_changes(fields, now, active, no_reminders)
        if updated.cuit and updated.cuit != current.cuit:
            other = self._clients.find_by_cuit(tenant_id, updated.cuit)
            if other is not None and other.id != client_id:
                raise CuitTakenError(updated.cuit)
        self._clients.save(updated)
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.USER,
                CuentasAction.CLIENT_UPDATED,
                {"client_id": str(client_id)},
                actor_profile_id=profile_id,
            )
        )
        return updated


class ListClients:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    def execute(
        self, tenant_id: UUID, q: str = "", missing_whatsapp: bool = False, page: int = 1
    ) -> ClientPage:
        return self._clients.search(tenant_id, q.strip(), missing_whatsapp, page, PAGE_SIZE)


class GetClient:
    def __init__(self, clients: ClientRepository) -> None:
        self._clients = clients

    def execute(self, tenant_id: UUID, client_id: UUID) -> ClientBalance:
        balance = self._clients.balance(tenant_id, client_id)
        if balance is None:
            raise ClientNotFoundError(str(client_id))
        return balance
