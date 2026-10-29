"""The Probalo simulator: tenant endpoints for the panel and admin endpoints for the
backoffice ("Probar su agente"). Both drive the same channel-agnostic agent runtime."""

import logging
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from followup_core.conversation.application.simulator import (
    GetSimulator,
    ResetSimulator,
    SendSimulatorMessage,
)
from followup_core.conversation.application.threads import ThreadView
from followup_core.conversation.domain.errors import (
    InvalidMessageError,
    LlmUnavailableError,
    SimulatorLimitReachedError,
)
from followup_core.conversation.domain.thread import MAX_MESSAGE_LENGTH, Message
from followup_core.identity.domain.profile import Profile
from followup_core.tenancy.application.get_tenant import GetTenant
from followup_core.tenancy.domain.agent_config import AgentConfig
from followup_core.tenancy.domain.errors import TenantNotFoundError
from pydantic import BaseModel, Field

from .auth import current_profile, require_platform_admin
from .http_errors import ApiError
from .leads.display import known_rows
from .tracing import trace_url

GetSimulatorFactory = Callable[..., GetSimulator]
SendMessageFactory = Callable[..., SendSimulatorMessage]
ResetSimulatorFactory = Callable[..., ResetSimulator]
GetTenantFactory = Callable[..., GetTenant]
OwnPropertiesFactory = Callable[..., Callable[[UUID], bool]]

logger = logging.getLogger("inmo24x7.simulator")


class ThreadRead(BaseModel):
    key: str
    agent_config_version: int
    created_at: datetime


class PropertyCardRead(BaseModel):
    id: str
    title: str
    address: str
    operation: Literal["sale", "rent"]
    zone: str
    price_label: str
    rooms: int
    link: str
    over_budget: bool
    is_sample: bool


class MessageRead(BaseModel):
    id: UUID
    direction: Literal["inbound", "outbound"]
    author: Literal["visitor", "agent", "human", "system"]
    text: str
    cards: list[PropertyCardRead] | None
    created_at: datetime
    # Only on admin endpoints, and only when the turn was traced and LANGSMITH_UI_URL is set.
    trace_url: str | None = None


class KnownFactRead(BaseModel):
    key: str
    label: str
    value: str | None


class SimulatorRead(BaseModel):
    thread: ThreadRead | None
    messages: list[MessageRead]
    known: list[KnownFactRead]
    uses_sample_properties: bool
    config_outdated: bool
    agent_name: str
    business_name: str


class SimulatorMessageWrite(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class SimulatorReplyRead(BaseModel):
    messages: list[MessageRead]
    known: list[KnownFactRead]


def _message_read(message: Message, trace_base: str = "") -> MessageRead:
    payload: dict[str, Any] = message.payload or {}
    cards = payload.get("cards")
    return MessageRead(
        id=message.id,
        direction=message.direction.value,  # type: ignore[arg-type]
        author=message.author.value,  # type: ignore[arg-type]
        text=message.text,
        cards=[PropertyCardRead(**card) for card in cards] if cards else None,
        created_at=message.created_at,
        trace_url=trace_url(trace_base, message.trace_run_id),
    )


def _known(config: AgentConfig, state: dict[str, Any] | Any) -> list[KnownFactRead]:
    return [
        KnownFactRead(key=row.key, label=row.label, value=row.value)
        for row in known_rows(config, state)
    ]


def _messages(messages: Sequence[Message], trace_base: str = "") -> list[MessageRead]:
    return [_message_read(message, trace_base) for message in messages]


def build_simulator_router(
    get_factory: GetSimulatorFactory,
    send_factory: SendMessageFactory,
    reset_factory: ResetSimulatorFactory,
    get_tenant_factory: GetTenantFactory,
    own_properties_factory: OwnPropertiesFactory,
    trace_ui_url_factory: Callable[[], str],
) -> APIRouter:
    router = APIRouter(tags=["simulator"])

    def simulator_read(
        view: ThreadView,
        tenant_id: UUID,
        get_tenant: GetTenant,
        own_properties: Callable[[UUID], bool],
        trace_base: str = "",
    ) -> SimulatorRead:
        thread = view.thread
        return SimulatorRead(
            thread=ThreadRead(
                key=str(thread.key),
                agent_config_version=thread.agent_config_version,
                created_at=thread.created_at,
            )
            if thread
            else None,
            messages=_messages(view.messages, trace_base),
            known=_known(view.agent_config, view.state),
            uses_sample_properties=not own_properties(tenant_id),
            config_outdated=view.config_outdated,
            agent_name=view.agent_config.agent_name,
            business_name=get_tenant.execute(tenant_id).name,
        )

    def send(
        use_case: SendSimulatorMessage,
        tenant_id: UUID,
        profile_id: UUID,
        text: str,
        trace_base: str = "",
    ) -> SimulatorReplyRead:
        started = time.perf_counter()
        try:
            turn = use_case.execute(tenant_id, profile_id, text)
        except InvalidMessageError as error:
            raise ApiError(422, "validation_error") from error
        except SimulatorLimitReachedError as error:
            raise ApiError(429, "simulator_limit_reached") from error
        except LlmUnavailableError as error:
            logger.warning(
                "agent_turn_failed",
                extra={
                    "tenant_id": str(tenant_id),
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "error": str(error),
                },
            )
            raise ApiError(503, "agent_unavailable") from error
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error

        # Never log message text: it is personal data.
        logger.info(
            "agent_turn",
            extra={
                "tenant_id": str(tenant_id),
                "thread_key": str(turn.thread.key),
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "model": turn.metrics.model,
                "prompt_versions": turn.metrics.prompt_versions,
                "input_tokens": turn.metrics.usage.input_tokens,
                "output_tokens": turn.metrics.usage.output_tokens,
                "trace_run_id": str(turn.trace_run_id) if turn.trace_run_id else None,
            },
        )
        return SimulatorReplyRead(
            messages=_messages(turn.outbound, trace_base),
            known=_known(turn.agent_config, turn.state),
        )

    def require_tenant(tenant_id: UUID, get_tenant: GetTenant) -> None:
        try:
            get_tenant.execute(tenant_id)
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error

    @router.get("/simulator", response_model=SimulatorRead)
    def get_simulator(
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[GetSimulator, Depends(get_factory)],
        get_tenant: Annotated[GetTenant, Depends(get_tenant_factory)],
        own_properties: Annotated[Callable[[UUID], bool], Depends(own_properties_factory)],
    ) -> SimulatorRead:
        view = use_case.execute(profile.tenant_id, profile.id)
        return simulator_read(view, profile.tenant_id, get_tenant, own_properties)

    @router.post("/simulator/messages", response_model=SimulatorReplyRead)
    def send_message(
        payload: SimulatorMessageWrite,
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[SendSimulatorMessage, Depends(send_factory)],
    ) -> SimulatorReplyRead:
        return send(use_case, profile.tenant_id, profile.id, payload.text)

    @router.post("/simulator/reset", response_model=SimulatorRead)
    def reset(
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[ResetSimulator, Depends(reset_factory)],
        get_tenant: Annotated[GetTenant, Depends(get_tenant_factory)],
        own_properties: Annotated[Callable[[UUID], bool], Depends(own_properties_factory)],
    ) -> SimulatorRead:
        view = use_case.execute(profile.tenant_id, profile.id)
        return simulator_read(view, profile.tenant_id, get_tenant, own_properties)

    @router.get("/admin/tenants/{tenant_id}/simulator", response_model=SimulatorRead)
    def admin_get_simulator(
        tenant_id: UUID,
        admin: Annotated[Profile, Depends(require_platform_admin)],
        use_case: Annotated[GetSimulator, Depends(get_factory)],
        get_tenant: Annotated[GetTenant, Depends(get_tenant_factory)],
        own_properties: Annotated[Callable[[UUID], bool], Depends(own_properties_factory)],
        trace_base: Annotated[str, Depends(trace_ui_url_factory)],
    ) -> SimulatorRead:
        require_tenant(tenant_id, get_tenant)
        view = use_case.execute(tenant_id, admin.id)
        return simulator_read(view, tenant_id, get_tenant, own_properties, trace_base)

    @router.post("/admin/tenants/{tenant_id}/simulator/messages", response_model=SimulatorReplyRead)
    def admin_send_message(
        tenant_id: UUID,
        payload: SimulatorMessageWrite,
        admin: Annotated[Profile, Depends(require_platform_admin)],
        use_case: Annotated[SendSimulatorMessage, Depends(send_factory)],
        get_tenant: Annotated[GetTenant, Depends(get_tenant_factory)],
        trace_base: Annotated[str, Depends(trace_ui_url_factory)],
    ) -> SimulatorReplyRead:
        require_tenant(tenant_id, get_tenant)
        return send(use_case, tenant_id, admin.id, payload.text, trace_base)

    @router.post("/admin/tenants/{tenant_id}/simulator/reset", response_model=SimulatorRead)
    def admin_reset(
        tenant_id: UUID,
        admin: Annotated[Profile, Depends(require_platform_admin)],
        use_case: Annotated[ResetSimulator, Depends(reset_factory)],
        get_tenant: Annotated[GetTenant, Depends(get_tenant_factory)],
        own_properties: Annotated[Callable[[UUID], bool], Depends(own_properties_factory)],
        trace_base: Annotated[str, Depends(trace_ui_url_factory)],
    ) -> SimulatorRead:
        require_tenant(tenant_id, get_tenant)
        view = use_case.execute(tenant_id, admin.id)
        return simulator_read(view, tenant_id, get_tenant, own_properties, trace_base)

    return router
