"""Templates in the business's WABA. Cloud connections call the Graph API with the
business's own token; log connections (local development) approve every template at once,
so the whole flow runs without Meta."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from followup_core.messaging.domain.connection import SenderKind, WhatsAppConnection
from followup_core.messaging.infrastructure.crypto import TokenCipher
from followup_core.messaging.infrastructure.graph import GraphClient


@dataclass(frozen=True, slots=True)
class MetaTemplate:
    """One template as Meta lists it."""

    id: str
    name: str
    language: str
    status: str
    rejected_reason: str | None = None


class TemplateGraph(Protocol):
    def create(self, connection: WhatsAppConnection, request: Mapping[str, Any]) -> tuple[str, str]:
        """(Meta's template id, its status). Raises SendError."""
        ...

    def list(self, connection: WhatsAppConnection) -> list[MetaTemplate]: ...


def _reason(value: Any) -> str | None:
    text = str(value or "").strip()
    return None if not text or text.upper() == "NONE" else text


class CloudTemplateGraph:
    def __init__(self, client: GraphClient, cipher: TokenCipher) -> None:
        self._client = client
        self._cipher = cipher

    def create(self, connection: WhatsAppConnection, request: Mapping[str, Any]) -> tuple[str, str]:
        token = self._cipher.decrypt(connection.access_token_encrypted)
        return self._client.create_message_template(connection.waba_id, token, request)

    def list(self, connection: WhatsAppConnection) -> list[MetaTemplate]:
        token = self._cipher.decrypt(connection.access_token_encrypted)
        return [
            MetaTemplate(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                language=str(item.get("language") or ""),
                status=str(item.get("status") or ""),
                rejected_reason=_reason(item.get("rejected_reason")),
            )
            for item in self._client.message_templates(connection.waba_id, token)
            if item.get("id")
        ]


class LogTemplateGraph:
    """Development: approved on creation; listing has nothing new to say."""

    def create(self, connection: WhatsAppConnection, request: Mapping[str, Any]) -> tuple[str, str]:
        return f"log-{uuid4().hex[:16]}", "APPROVED"

    def list(self, connection: WhatsAppConnection) -> list[MetaTemplate]:
        return []


TemplateGraphFor = Callable[[WhatsAppConnection], TemplateGraph]


def template_graph_for(client: GraphClient, cipher: TokenCipher) -> TemplateGraphFor:
    def choose(connection: WhatsAppConnection) -> TemplateGraph:
        if connection.sender is SenderKind.CLOUD:
            return CloudTemplateGraph(client, cipher)
        return LogTemplateGraph()

    return choose
