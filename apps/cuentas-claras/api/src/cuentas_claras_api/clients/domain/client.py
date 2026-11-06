"""A client: the company that owes the invoices. Reminders (Day 9) go to its WhatsApp."""

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from followup_core.messaging.domain.phones import to_e164

from .cuit import parse_cuit
from .errors import ClientInvalidError

MAX_NAME = 200
MAX_TEXT = 200
MAX_NOTES = 2000
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def name_key(name: str) -> str:
    """How two names count as the same client: accents, case, punctuation and spacing
    folded ("Edificio  Güemes S.A." == "edificio guemes sa")."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    words = re.sub(r"[^a-z0-9]+", " ", ascii_name.lower().replace(".", "")).split()
    return " ".join(words)


@dataclass(frozen=True, slots=True)
class ClientFields:
    """What a person types or a spreadsheet row carries; validated by `Client.create` and
    `Client.with_changes`."""

    name: str
    subtitle: str = ""
    cuit: str = ""
    contact_name: str = ""
    whatsapp: str = ""
    email: str = ""
    notes: str = ""


def _text(value: str, field: str, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) > limit:
        raise ClientInvalidError(field)
    return text


def validate_fields(fields: ClientFields) -> dict[str, str | None]:
    name = _text(fields.name, "name", MAX_NAME)
    if not name:
        raise ClientInvalidError("name")
    whatsapp = None
    if fields.whatsapp.strip():
        whatsapp = to_e164(fields.whatsapp)
        if whatsapp is None:
            raise ClientInvalidError("whatsapp")
    email = fields.email.strip().lower() or None
    if email is not None and not _EMAIL.fullmatch(email):
        raise ClientInvalidError("email")
    notes = fields.notes.strip()
    if len(notes) > MAX_NOTES:
        raise ClientInvalidError("notes")
    return {
        "name": name,
        "subtitle": _text(fields.subtitle, "subtitle", MAX_TEXT) or None,
        "cuit": parse_cuit(fields.cuit) if fields.cuit.strip() else None,
        "contact_name": _text(fields.contact_name, "contact_name", MAX_TEXT) or None,
        "whatsapp": whatsapp,
        "email": email,
        "notes": notes or None,
    }


@dataclass(frozen=True, slots=True)
class Client:
    id: UUID
    tenant_id: UUID
    name: str
    subtitle: str | None
    # The 11 digits, unique per business when present.
    cuit: str | None
    contact_name: str | None
    # E.164 ("+5491155550188"), normalized with core's phone rules.
    whatsapp: str | None
    email: str | None
    notes: str | None
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, tenant_id: UUID, fields: ClientFields, now: datetime) -> "Client":
        return cls(
            id=uuid4(),
            tenant_id=tenant_id,
            active=True,
            created_at=now,
            updated_at=now,
            **validate_fields(fields),  # type: ignore[arg-type]
        )

    def with_changes(
        self, fields: ClientFields, now: datetime, active: bool | None = None
    ) -> "Client":
        return replace(
            self,
            updated_at=now,
            active=self.active if active is None else active,
            **validate_fields(fields),  # type: ignore[arg-type]
        )

    @property
    def name_key(self) -> str:
        return name_key(self.name)

    @property
    def missing_whatsapp(self) -> bool:
        """Reminders need a WhatsApp number ("Sin WhatsApp" in the panel)."""
        return self.whatsapp is None
