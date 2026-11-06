from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from .client import Client


@dataclass(frozen=True, slots=True)
class ClientBalance:
    """A client with what it owes: its open invoices, per currency."""

    client: Client
    open_invoices: int
    owed_ars: Decimal
    owed_usd: Decimal


@dataclass(frozen=True, slots=True)
class ClientPage:
    items: Sequence[ClientBalance]
    total: int
    page: int
    page_size: int


class ClientRepository(Protocol):
    def get(self, tenant_id: UUID, client_id: UUID) -> Client | None: ...

    def find_by_cuit(self, tenant_id: UUID, cuit: str) -> Client | None: ...

    def find_by_name_key(self, tenant_id: UUID, name_key: str) -> Client | None: ...

    def add(self, client: Client) -> None: ...

    def save(self, client: Client) -> None: ...

    def search(
        self, tenant_id: UUID, q: str, missing_whatsapp: bool, page: int, page_size: int
    ) -> ClientPage: ...

    def balance(self, tenant_id: UUID, client_id: UUID) -> ClientBalance | None: ...
