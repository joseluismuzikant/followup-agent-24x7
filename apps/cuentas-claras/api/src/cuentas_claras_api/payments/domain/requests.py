"""A payment request: one or more open invoices of one client behind one unguessable link,
`https://<panel>/p/<token>`. A reminder for several invoices is one request. Day 9B adds
the Mercado Pago checkout to the same request (its preference and payments); here it only
shows what is owed and the business's transfer details.

The token is 32 random bytes, URL-safe (256 bits). The request keeps only its SHA-256 and
is looked up by it; an unknown and an expired token look the same to the page."""

import hashlib
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

TOKEN_BYTES = 32
VALIDITY = timedelta(days=60)
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{40,64}$")


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def looks_like_token(token: str) -> bool:
    return bool(_TOKEN.fullmatch(token))


@dataclass(frozen=True, slots=True)
class PaymentRequest:
    id: UUID
    tenant_id: UUID
    client_id: UUID
    invoice_ids: tuple[UUID, ...]
    token_hash: str
    created_at: datetime
    expires_at: datetime

    @classmethod
    def create(
        cls, tenant_id: UUID, client_id: UUID, invoice_ids: Sequence[UUID], now: datetime
    ) -> tuple["PaymentRequest", str]:
        """The request and its token (the token is only in the link, never stored)."""
        if not invoice_ids:
            raise ValueError("A payment request needs at least one invoice.")
        token = new_token()
        request = cls(
            id=uuid4(),
            tenant_id=tenant_id,
            client_id=client_id,
            invoice_ids=tuple(dict.fromkeys(invoice_ids)),
            token_hash=token_hash(token),
            created_at=now,
            expires_at=now + VALIDITY,
        )
        return request, token

    def expired(self, now: datetime) -> bool:
        return now >= self.expires_at


@dataclass(frozen=True, slots=True)
class TransferDetails:
    """ "Datos para transferencia" (Configuración): shown on the payment page."""

    tenant_id: UUID
    cbu_or_alias: str
    holder: str
    bank: str | None = None


class TransferDetailsInvalidError(ValueError):
    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


_ALIAS = re.compile(r"^[A-Za-z0-9.\-]{6,20}$")


def validate_transfer(
    tenant_id: UUID, cbu_or_alias: str, holder: str, bank: str | None
) -> TransferDetails:
    """A CBU/CVU is 22 digits; an alias 6–20 letters, digits, dots or hyphens."""
    value = "".join(cbu_or_alias.split())
    if not (value.isdigit() and len(value) == 22) and not _ALIAS.fullmatch(value):
        raise TransferDetailsInvalidError("cbu_or_alias")
    name = " ".join(holder.split())
    if not name or len(name) > 120:
        raise TransferDetailsInvalidError("holder")
    bank_name = " ".join((bank or "").split()) or None
    if bank_name is not None and len(bank_name) > 80:
        raise TransferDetailsInvalidError("bank")
    return TransferDetails(tenant_id, value, name, bank_name)
