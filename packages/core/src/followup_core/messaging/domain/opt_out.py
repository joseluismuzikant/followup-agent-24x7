""" "BAJA": a person who does not want the business to write to them again.

WhatsApp's policy requires honoring every opt-out. The deterministic matcher catches the
clear phrases before the agent runs ("BAJA", "STOP", "no me escriban más", ...), so they
work even while the team has the conversation or the model is down; an agent may add its
own reading for the less obvious ones. A word like "baja" inside another meaning ("¿la
planta baja está disponible?") is never enough on its own.

The flag is per business and per contact (the WhatsApp wa_id): another business can still
talk to the same number.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

OPT_OUT_CONFIRMATION = (
    "Listo, no te vamos a escribir más. Si algún día querés volver a consultar, escribinos."
)
# The error code of a part that was not sent because the contact asked not to be written to.
DO_NOT_CONTACT = "do_not_contact"

# A message that is only one of these (plus polite filler) is an opt-out.
_KEYWORDS = frozenset({"baja", "stop", "unsubscribe"})
_FILLER = frozenset(
    {"por", "favor", "porfa", "porfis", "xfa", "plis", "please", "gracias", "ok", "ya"}
)
# Clear phrases anywhere in the message (words without accents, lowercase).
_PHRASES = (
    "no me escriban mas",
    "no me escribas mas",
    "no me escriban nunca mas",
    "no me escriban nunca",
    "no quiero que me contacten",
    "no quiero que me contactes",
    "no quiero que me escriban",
    "no quiero recibir mas mensajes",
    "no quiero recibir mensajes",
    "no me contacten mas",
    "no me contacten",
    "no me manden mas mensajes",
    "no me envien mas mensajes",
    "dejen de escribirme",
    "deja de escribirme",
    "dejen de mandarme mensajes",
    "dejen de contactarme",
    "darme de baja",
    "dame de baja",
    "denme de baja",
    "me doy de baja",
    "pido la baja",
    "quiero la baja",
)
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _words(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return [word for word in _NON_WORD.split(plain) if word]


def is_opt_out(text: str) -> bool:
    """True for a clear request not to be written to again ("BAJA", "Stop!", "no me
    escriban más", "dejen de escribirme por favor"); accents, case and punctuation do not
    matter. "baja" with any other content ("planta baja", "¿baja el precio?") is not."""
    words = _words(text)
    if not words:
        return False
    if any(word in _KEYWORDS for word in words) and all(
        word in _KEYWORDS or word in _FILLER for word in words
    ):
        return True
    joined = f" {' '.join(words)} "
    return any(f" {phrase} " in joined for phrase in _PHRASES)


class ContactOptedOutError(Exception):
    """The business may not write to this contact: they asked not to be written to."""


class OptOutSource(StrEnum):
    """Who set or lifted the flag: the person's own message, the team in the panel, or a
    platform admin in the backoffice (a request that arrived by email or phone)."""

    MESSAGE = "message"
    TEAM = "team"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class DoNotContact:
    tenant_id: UUID
    wa_id: str
    created_at: datetime
    source: OptOutSource
    # The wamid of the "BAJA" message; None when set by a person.
    source_message_id: str | None = None
    set_by_profile_id: UUID | None = None
    # The one confirmation that may still go out after the flag is set.
    confirmation_message_id: UUID | None = None


class DoNotContactRepository(Protocol):
    def get(self, tenant_id: UUID, wa_id: str) -> DoNotContact | None: ...

    def add(self, entry: DoNotContact) -> None:
        """Replaces the business's entry for that contact, if any."""
        ...

    def remove(self, tenant_id: UUID, wa_id: str) -> bool:
        """True when there was an entry."""
        ...
