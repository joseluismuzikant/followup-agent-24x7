"""Builds the integrations' use cases and job handlers on a session. The HTTP clients
(Tokko, the webhook) are process-wide; tests replace them with fakes (`get_clients`)."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

from followup_core.messaging.infrastructure.models import WhatsAppConnectionModel
from followup_core.scheduling.domain.jobs import JobHandler
from followup_core.scheduling.infrastructure.queue import SqlAlchemyJobQueue
from followup_core.tenancy.infrastructure.audit_repository import SqlAlchemyAuditLog
from followup_core.tenancy.infrastructure.setup_repositories import (
    SqlAlchemyBusinessSettingsRepository,
)
from followup_platform.whatsapp.wiring import MessagingServices, tenant_is_active
from followup_platform.whatsapp.wiring import business_name as tenant_name
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..leads.application.notify import HANDED_OFF_JOB
from ..leads.application.queries import GetLead
from ..leads.domain.sinks import LeadSink
from ..product import PRODUCT
from ..properties.infrastructure.repositories import SqlAlchemyPropertyRepository
from .application import (
    DELIVER_JOB,
    SYNC_JOB,
    SYNC_SWEEP_JOB,
    ConfigureWebhook,
    ConnectTokko,
    DeleteWebhook,
    DeliverLead,
    DisconnectTokko,
    GetIntegrations,
    GetPublicWidget,
    IntegrationUseCases,
    QueueLeadDeliveries,
    RequestTokkoSync,
    RotateWebhookSecret,
    SaveWidget,
    SendWebhookTest,
    Stores,
    SweepTokkoSyncs,
    SyncProperties,
    SyncTokko,
    UpdateTokko,
    utc_now,
)
from .domain import Integration, Provider
from .qualified import BuildQualifiedLead
from .repositories import (
    SqlAlchemyDeliveryRepository,
    SqlAlchemyIntegrationRepository,
    SqlAlchemySyncReportRepository,
)
from .tokko import DEFAULT_BASE_URL, TokkoClient, TokkoLeadSink, TokkoPropertySource
from .webhook import WebhookClient, WebhookLeadSink


@dataclass(frozen=True, slots=True)
class IntegrationClients:
    tokko: TokkoClient
    webhook: WebhookClient


@lru_cache
def get_clients() -> IntegrationClients:
    return IntegrationClients(
        tokko=TokkoClient(os.getenv("TOKKO_API_URL", "").strip() or DEFAULT_BASE_URL),
        webhook=WebhookClient(),
    )


def stores(
    session: Session, services: MessagingServices, clock: Callable[[], datetime] = utc_now
) -> Stores:
    return Stores(
        integrations=SqlAlchemyIntegrationRepository(session),
        reports=SqlAlchemySyncReportRepository(session),
        deliveries=SqlAlchemyDeliveryRepository(session),
        cipher=services.cipher,
        queue=SqlAlchemyJobQueue(session, clock, PRODUCT),
        audit=SqlAlchemyAuditLog(session),
        clock=clock,
    )


def whatsapp_number(session: Session) -> Callable[[UUID], str | None]:
    """The connected number shown on the button (None while not connected)."""

    def number(tenant_id: UUID) -> str | None:
        return session.scalar(
            select(WhatsAppConnectionModel.display_phone_number).where(
                WhatsAppConnectionModel.tenant_id == tenant_id,
                WhatsAppConnectionModel.status == "connected",
                WhatsAppConnectionModel.display_phone_number.is_not(None),
            )
        )

    return number


def _local(panel_url: str) -> bool:
    return any(host in panel_url for host in ("://localhost", "://127.0.0.1"))


def use_cases(
    session: Session,
    services: MessagingServices,
    clients: IntegrationClients,
    clock: Callable[[], datetime] = utc_now,
) -> IntegrationUseCases:
    bundle = stores(session, services, clock)
    panel_url = services.settings.panel_url

    def ping(item: Integration, secret: str, delivery_id: UUID) -> Any:
        sink = WebhookLeadSink(clients.webhook, str(item.options["url"]), secret, clock)
        return sink.ping(item.tenant_id, delivery_id, panel_url)

    return IntegrationUseCases(
        get=GetIntegrations(bundle),
        connect_tokko=ConnectTokko(bundle, clients.tokko.check),
        update_tokko=UpdateTokko(bundle),
        disconnect_tokko=DisconnectTokko(bundle),
        sync_tokko=RequestTokkoSync(bundle),
        configure_webhook=ConfigureWebhook(bundle, allow_http=_local(panel_url)),
        rotate_secret=RotateWebhookSecret(bundle),
        delete_webhook=DeleteWebhook(bundle),
        test_webhook=SendWebhookTest(bundle, ping),
        save_widget=SaveWidget(bundle),
        deliveries=bundle.deliveries,
        whatsapp_number=whatsapp_number(session),
    )


def public_widget(session: Session) -> GetPublicWidget:
    return GetPublicWidget(
        SqlAlchemyIntegrationRepository(session),
        tenant_name(session),
        whatsapp_number(session),
        tenant_is_active(session),
    )


def job_handlers(
    session: Session,
    services: MessagingServices,
    get_lead: GetLead,
    clients: IntegrationClients | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> list[tuple[str, JobHandler]]:
    clients = clients or get_clients()
    bundle = stores(session, services, clock)
    is_active = tenant_is_active(session)
    properties = SqlAlchemyPropertyRepository(session)
    qualified = BuildQualifiedLead(
        get_lead,
        properties,
        SqlAlchemyBusinessSettingsRepository(session),
        services.settings.panel_url,
    )

    def sink_for(item: Integration, secret: str) -> LeadSink:
        if item.provider is Provider.TOKKO:
            return TokkoLeadSink(clients.tokko, secret)
        return WebhookLeadSink(clients.webhook, str(item.options["url"]), secret, clock)

    return [
        (SYNC_SWEEP_JOB, SweepTokkoSyncs(bundle)),
        (
            SYNC_JOB,
            SyncTokko(
                bundle,
                SyncProperties(properties, clock),
                lambda key: TokkoPropertySource(clients.tokko, key),
                is_active,
            ),
        ),
        (HANDED_OFF_JOB, QueueLeadDeliveries(bundle, is_active)),
        (DELIVER_JOB, DeliverLead(bundle, qualified.execute, sink_for)),
    ]
