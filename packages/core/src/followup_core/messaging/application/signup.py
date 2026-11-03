"""Embedded Signup: the customer connects their own number from the panel (S4).

The web gets a 30-second code and the WABA / phone number ids from Meta's popup and posts
them here at once. Steps: exchange the code for the business token, subscribe our app to
the WABA, register the number with a PIN of ours, read the number, save the connection.
Every step is recorded; a retry starts after the last one that worked.
"""

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID, uuid4

from followup_core.conversation.application.threads import Clock, utc_now
from followup_core.tenancy.domain.audit import ActorKind, AuditAction, AuditEvent, AuditLog

from ..domain.connection import (
    BusinessVerification,
    ConnectionStatus,
    SenderKind,
    WhatsAppConnection,
)
from ..domain.outbound import SendError
from ..domain.repositories import ConnectionRepository
from ..domain.signup import Signup, SignupRepository, SignupStep, reached
from .connections import (
    _ID,
    ConnectionDefaults,
    ConnectionInvalidError,
    PhoneInfo,
    PhoneNumberTakenError,
)
from .health import ConnectionHealth

logger = logging.getLogger("followup.whatsapp")


class SignupGraph(Protocol):
    """The Graph calls of Embedded Signup, with the raw business token."""

    def exchange_code(self, code: str) -> str: ...

    def subscribe_app(self, waba_id: str, token: str) -> None: ...

    def register(self, phone_number_id: str, token: str, pin: str) -> None: ...

    def phone_number(self, phone_number_id: str, token: str) -> PhoneInfo: ...

    def business_verification(self, business_id: str, token: str) -> BusinessVerification: ...


class Cipher(Protocol):
    def encrypt(self, token: str) -> str: ...

    def decrypt(self, stored: str) -> str: ...


class SignupFailedError(Exception):
    """A step failed; progress up to it is stored. `meta_code` is Meta's code."""

    def __init__(self, step: SignupStep, meta_code: str) -> None:
        super().__init__(f"{step}:{meta_code}")
        self.step = step
        self.meta_code = meta_code


class SignupRestartError(Exception):
    """A retry without a code, but the token was never obtained: run Meta's popup again."""


@dataclass(frozen=True, slots=True)
class SignupRequest:
    waba_id: str
    phone_number_id: str
    business_id: str | None = None
    code: str | None = None  # None: retry with the stored token


def new_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class CompleteEmbeddedSignup:
    def __init__(
        self,
        signups: SignupRepository,
        connections: ConnectionRepository,
        graph: SignupGraph,
        cipher: Cipher,
        defaults: ConnectionDefaults,
        health: ConnectionHealth,
        audit: AuditLog,
        clock: Clock = utc_now,
        pin: Callable[[], str] = new_pin,
    ) -> None:
        self._signups = signups
        self._connections = connections
        self._graph = graph
        self._cipher = cipher
        self._defaults = defaults
        self._health = health
        self._audit = audit
        self._clock = clock
        self._pin = pin

    def execute(
        self, tenant_id: UUID, request: SignupRequest, actor_profile_id: UUID | None = None
    ) -> WhatsAppConnection:
        waba_id, phone_number_id = request.waba_id.strip(), request.phone_number_id.strip()
        business_id = (request.business_id or "").strip() or None
        if not _ID.fullmatch(waba_id) or not _ID.fullmatch(phone_number_id):
            raise ConnectionInvalidError("waba_id and phone_number_id are short ids.")
        if business_id is not None and not _ID.fullmatch(business_id):
            raise ConnectionInvalidError("business_id is a short id.")
        other = self._connections.get_by_phone_number_id(phone_number_id)
        if other is not None and other.tenant_id != tenant_id:
            raise PhoneNumberTakenError(phone_number_id)

        current = self._connections.get_by_tenant(tenant_id)
        if (
            request.code is None
            and current is not None
            and current.phone_number_id == phone_number_id
            and current.is_connected
            and current.sender is SenderKind.CLOUD
        ):
            return current  # already done: a retry changes nothing

        signup = self._start(tenant_id, waba_id, phone_number_id, business_id, request.code)
        try:
            signup = self._run(signup, request.code)
        except SendError as error:
            raise self._failed(signup, error, actor_profile_id) from error
        return self._connect(signup, actor_profile_id)

    def _failed(
        self, started: Signup, error: SendError, actor_profile_id: UUID | None
    ) -> SignupFailedError:
        """Keeps the progress (each step saved as it completed) and the failing step."""
        progress = self._signups.get(started.tenant_id) or started
        step = _next(progress.step)
        now = self._clock()
        self._signups.save(replace(progress, last_error_code=error.code[:40], updated_at=now))
        self._audit.record(
            AuditEvent(
                started.tenant_id,
                now,
                ActorKind.USER if actor_profile_id else ActorKind.ADMIN,
                AuditAction.WHATSAPP_SIGNUP_FAILED,
                {"step": step.value, "meta_code": error.code[:40]},
                actor_profile_id=actor_profile_id,
            )
        )
        logger.warning(
            "whatsapp_signup_failed", extra={"step": step.value, "meta_code": error.code}
        )
        return SignupFailedError(step, error.code)

    def _start(
        self,
        tenant_id: UUID,
        waba_id: str,
        phone_number_id: str,
        business_id: str | None,
        code: str | None,
    ) -> Signup:
        stored = self._signups.get(tenant_id)
        same = (
            stored is not None
            and stored.waba_id == waba_id
            and stored.phone_number_id == phone_number_id
        )
        if code is None:
            # A retry: only from what is stored, and only if the token was obtained.
            if stored is None or not same or stored.token_encrypted is None:
                raise SignupRestartError(str(tenant_id))
            return stored
        # A new code always starts over (a new token); the PIN stays the tenant's.
        signup = Signup(
            tenant_id=tenant_id,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            business_id=business_id or (stored.business_id if same and stored else None),
            step=SignupStep.STARTED,
            pin_encrypted=stored.pin_encrypted if stored else self._cipher.encrypt(self._pin()),
            updated_at=self._clock(),
        )
        self._signups.save(signup)
        return signup

    def _run(self, signup: Signup, code: str | None) -> Signup:
        if not reached(signup.step, SignupStep.EXCHANGED):
            if code is None:
                raise SignupRestartError(str(signup.tenant_id))
            token = self._graph.exchange_code(code)
            signup = self._advance(signup, SignupStep.EXCHANGED, self._cipher.encrypt(token))
        assert signup.token_encrypted is not None
        token = self._cipher.decrypt(signup.token_encrypted)
        if not reached(signup.step, SignupStep.SUBSCRIBED):
            self._graph.subscribe_app(signup.waba_id, token)
            signup = self._advance(signup, SignupStep.SUBSCRIBED)
        if not reached(signup.step, SignupStep.REGISTERED):
            pin = self._cipher.decrypt(signup.pin_encrypted)
            self._graph.register(signup.phone_number_id, token, pin)
            signup = self._advance(signup, SignupStep.REGISTERED)
        return signup

    def _advance(self, signup: Signup, step: SignupStep, token: str | None = None) -> Signup:
        updated = replace(
            signup,
            step=step,
            token_encrypted=token or signup.token_encrypted,
            last_error_code=None,
            updated_at=self._clock(),
        )
        self._signups.save(updated)
        return updated

    def _connect(self, signup: Signup, actor_profile_id: UUID | None) -> WhatsAppConnection:
        assert signup.token_encrypted is not None
        token = self._cipher.decrypt(signup.token_encrypted)
        try:
            info = self._graph.phone_number(signup.phone_number_id, token)
        except SendError as error:
            raise self._failed(signup, error, actor_profile_id) from error
        verification = (
            self._graph.business_verification(signup.business_id, token)
            if signup.business_id
            else BusinessVerification.UNKNOWN
        )
        now = self._clock()
        current = self._connections.get_by_tenant(signup.tenant_id)
        base = current or WhatsAppConnection(
            id=uuid4(),
            tenant_id=signup.tenant_id,
            phone_number_id=signup.phone_number_id,
            waba_id=signup.waba_id,
            access_token_encrypted=signup.token_encrypted,
            sender=SenderKind.CLOUD,
            template_name=self._defaults.template_name,
            template_language=self._defaults.template_language,
            status=ConnectionStatus.CONNECTED,
            updated_at=now,
        )
        connection = replace(
            base,
            phone_number_id=signup.phone_number_id,
            waba_id=signup.waba_id,
            business_id=signup.business_id,
            access_token_encrypted=signup.token_encrypted,
            sender=SenderKind.CLOUD,
            display_phone_number=info.display_phone_number or None,
            verified_name=info.verified_name or None,
            quality_rating=info.quality_rating,
            name_status=info.name_status,
            business_verification=verification,
            status=ConnectionStatus.CONNECTED,
            last_error_code=None,
            failing_since=None,
            connected_at=base.connected_at or now,
            last_health_check_at=now,
            updated_at=now,
        )
        self._connections.save(connection)
        self._signups.save(replace(signup, step=SignupStep.CONNECTED, updated_at=now))
        self._audit.record(
            AuditEvent(
                signup.tenant_id,
                now,
                ActorKind.USER if actor_profile_id else ActorKind.ADMIN,
                AuditAction.WHATSAPP_CONNECTED,
                {
                    "source": "embedded_signup",
                    "phone_number_id": signup.phone_number_id,
                    "waba_id": signup.waba_id,
                },
                actor_profile_id=actor_profile_id,
            )
        )
        self._health.resume(signup.tenant_id)
        return connection


def _next(step: SignupStep) -> SignupStep:
    order = list(SignupStep)
    return order[min(order.index(step) + 1, len(order) - 1)]
