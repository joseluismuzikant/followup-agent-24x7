"""Connecting a WhatsApp number by hand (backoffice). Day 7 adds Embedded Signup on top."""

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID, uuid4

from followup_core.conversation.application.threads import Clock, utc_now

from ..domain.connection import ConnectionStatus, SenderKind, WhatsAppConnection
from ..domain.outbound import SendError, WhatsAppSender
from ..domain.phones import to_e164
from ..domain.repositories import ConnectionRepository

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TEMPLATE = re.compile(r"^[a-z0-9_]{1,100}$")
MAX_TOKEN_LENGTH = 4096


class ConnectionInvalidError(ValueError):
    pass


class PhoneNumberTakenError(ValueError):
    pass


class ConnectionNotFoundError(LookupError):
    pass


class WhatsAppApiError(Exception):
    """A Graph API call failed; `meta_code` is Meta's error code (shown to admins only)."""

    def __init__(self, meta_code: str) -> None:
        super().__init__(meta_code)
        self.meta_code = meta_code


@dataclass(frozen=True, slots=True)
class PhoneInfo:
    display_phone_number: str
    verified_name: str


class GraphPort(Protocol):
    def phone_number(self, connection: WhatsAppConnection) -> PhoneInfo: ...

    def subscribe_app(self, connection: WhatsAppConnection) -> None: ...


class Encrypt(Protocol):
    def __call__(self, token: str) -> str: ...


@dataclass(frozen=True, slots=True)
class ConnectionDraft:
    phone_number_id: str
    waba_id: str
    display_phone_number: str | None = None
    # None keeps the stored token (it is never sent back to the form).
    access_token: str | None = None
    sender: SenderKind | None = None
    # None keeps the stored value; "" removes the visit confirmation template.
    visit_template_name: str | None = None
    visit_template_language: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectionDefaults:
    sender: SenderKind
    template_name: str
    template_language: str


class SaveConnection:
    def __init__(
        self,
        connections: ConnectionRepository,
        encrypt: Encrypt,
        defaults: ConnectionDefaults,
        clock: Clock = utc_now,
    ) -> None:
        self._connections = connections
        self._encrypt = encrypt
        self._defaults = defaults
        self._clock = clock

    def execute(self, tenant_id: UUID, draft: ConnectionDraft) -> WhatsAppConnection:
        phone_number_id, waba_id = draft.phone_number_id.strip(), draft.waba_id.strip()
        if not _ID.fullmatch(phone_number_id) or not _ID.fullmatch(waba_id):
            raise ConnectionInvalidError("phone_number_id and waba_id are short ids.")
        token = (draft.access_token or "").strip()
        if len(token) > MAX_TOKEN_LENGTH or (draft.access_token is not None and not token):
            raise ConnectionInvalidError("Invalid access token.")
        visit_template = _template_name(draft.visit_template_name)
        other = self._connections.get_by_phone_number_id(phone_number_id)
        if other is not None and other.tenant_id != tenant_id:
            raise PhoneNumberTakenError(phone_number_id)

        now = self._clock()
        current = self._connections.get_by_tenant(tenant_id)
        if current is None:
            if not token:
                raise ConnectionInvalidError("A new connection needs an access token.")
            connection = WhatsAppConnection(
                id=uuid4(),
                tenant_id=tenant_id,
                phone_number_id=phone_number_id,
                waba_id=waba_id,
                access_token_encrypted=self._encrypt(token),
                sender=draft.sender or self._defaults.sender,
                template_name=self._defaults.template_name,
                template_language=self._defaults.template_language,
                status=ConnectionStatus.CONNECTED,
                updated_at=now,
                display_phone_number=draft.display_phone_number,
                connected_at=now,
                visit_template_name=visit_template or None,
                visit_template_language=draft.visit_template_language or "es_AR",
            )
        else:
            connection = replace(
                current,
                phone_number_id=phone_number_id,
                waba_id=waba_id,
                display_phone_number=draft.display_phone_number or current.display_phone_number,
                access_token_encrypted=(
                    self._encrypt(token) if token else current.access_token_encrypted
                ),
                sender=draft.sender or current.sender,
                status=ConnectionStatus.CONNECTED,
                last_error_code=None,
                connected_at=current.connected_at or now,
                updated_at=now,
                visit_template_name=(
                    current.visit_template_name
                    if visit_template is None
                    else visit_template or None
                ),
                visit_template_language=(
                    draft.visit_template_language or current.visit_template_language
                ),
            )
        self._connections.save(connection)
        return connection


def _template_name(value: str | None) -> str | None:
    """Meta template names are lowercase letters, digits and underscores."""
    if value is None:
        return None
    name = value.strip()
    if name and not _TEMPLATE.fullmatch(name):
        raise ConnectionInvalidError("Invalid template name.")
    return name


class ManageConnection:
    """Probar conexión, Suscribir la app, Enviar mensaje de prueba, Desconectar."""

    def __init__(
        self,
        connections: ConnectionRepository,
        graph_for: Callable[[WhatsAppConnection], GraphPort],
        sender_for: Callable[[WhatsAppConnection], WhatsAppSender],
        clock: Clock = utc_now,
    ) -> None:
        self._connections = connections
        self._graph_for = graph_for
        self._sender_for = sender_for
        self._clock = clock

    def get(self, tenant_id: UUID) -> WhatsAppConnection | None:
        return self._connections.get_by_tenant(tenant_id)

    def _require(self, tenant_id: UUID) -> WhatsAppConnection:
        connection = self._connections.get_by_tenant(tenant_id)
        if connection is None:
            raise ConnectionNotFoundError(str(tenant_id))
        return connection

    def _failed(self, connection: WhatsAppConnection, error: SendError) -> WhatsAppApiError:
        self._connections.save(connection.with_error(error.code, self._clock()))
        return WhatsAppApiError(error.code)

    def test(self, tenant_id: UUID) -> WhatsAppConnection:
        connection = self._require(tenant_id)
        try:
            info = self._graph_for(connection).phone_number(connection)
        except SendError as error:
            raise self._failed(connection, error) from error
        updated = replace(
            connection,
            display_phone_number=info.display_phone_number or connection.display_phone_number,
            verified_name=info.verified_name or connection.verified_name,
            status=ConnectionStatus.CONNECTED,
            last_error_code=None,
            updated_at=self._clock(),
        )
        self._connections.save(updated)
        return updated

    def subscribe(self, tenant_id: UUID) -> WhatsAppConnection:
        connection = self._require(tenant_id)
        try:
            self._graph_for(connection).subscribe_app(connection)
        except SendError as error:
            raise self._failed(connection, error) from error
        return connection

    def send_test_message(self, tenant_id: UUID, to: str) -> str:
        """The connection's template to a number typed by an admin (Meta test numbers come
        with "hello_world" in en_US). Returns the wamid."""
        connection = self._require(tenant_id)
        e164 = to_e164(to)
        if e164 is None:
            raise ConnectionInvalidError("Invalid phone number.")
        sender = self._sender_for(connection)
        try:
            return sender.send_template(
                connection, e164.lstrip("+"), connection.template_name, connection.template_language
            )
        except SendError as error:
            raise self._failed(connection, error) from error

    def disconnect(self, tenant_id: UUID) -> WhatsAppConnection:
        connection = self._require(tenant_id)
        updated = replace(
            connection, status=ConnectionStatus.DISCONNECTED, updated_at=self._clock()
        )
        self._connections.save(updated)
        return updated
