"""How a product API wires WhatsApp: the process-wide clients and the use cases and job
handlers built from them, for one product. Each product's container calls these with its
key, so its webhook, health sweep, reconnect emails and jobs stay on its own businesses
and queue. What differs per product (what an inbound message does, the email copy) is
passed in."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from followup_core.identity.infrastructure.models import ProfileModel
from followup_core.messaging.application.connections import (
    ConnectionDefaults,
    GraphPort,
    ManageConnection,
    SaveConnection,
)
from followup_core.messaging.application.health import (
    HEALTH_CHECK_JOB,
    HEALTH_SWEEP_JOB,
    ApplyAccountUpdate,
    ConnectionHealth,
    HealthCheck,
    HealthSweep,
)
from followup_core.messaging.application.pipeline import (
    MARK_READ_JOB,
    SEND_JOB,
    ApplyDeliveryStatus,
    IngestWebhook,
    MarkRead,
    SenderFor,
    SendQueued,
    TemplateUpdates,
)
from followup_core.messaging.application.reconnect import (
    RECONNECT_EMAIL_JOB,
    RequestReconnectLink,
    SendReconnectEmail,
)
from followup_core.messaging.application.signup import CompleteEmbeddedSignup
from followup_core.messaging.domain.connection import SenderKind, WhatsAppConnection
from followup_core.messaging.domain.outbound import WhatsAppSender
from followup_core.messaging.domain.signup import Signup
from followup_core.messaging.infrastructure.crypto import TokenCipher
from followup_core.messaging.infrastructure.graph import (
    CloudApiSender,
    CloudGraphPort,
    CloudSignupGraph,
    GraphClient,
    LogGraphPort,
)
from followup_core.messaging.infrastructure.log_sender import LOG_STATUS_JOB, LogSender
from followup_core.messaging.infrastructure.repositories import (
    SqlAlchemyConnectionRepository,
    SqlAlchemyInboundEventRepository,
    SqlAlchemyOutboundRepository,
    SqlAlchemySignupRepository,
)
from followup_core.notifications.domain.email import EmailSender
from followup_core.notifications.infrastructure.smtp import SmtpEmailSender, SmtpSettings
from followup_core.scheduling.domain.jobs import Job, JobHandler
from followup_core.scheduling.infrastructure.queue import SqlAlchemyJobQueue
from followup_core.tenancy.domain.product import Product
from followup_core.tenancy.domain.tenant import TenantStatus
from followup_core.tenancy.infrastructure.audit_repository import SqlAlchemyAuditLog
from followup_core.tenancy.infrastructure.models import TenantModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..settings import Settings

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class MessagingServices:
    """Process-wide clients, built once. Tests replace the whole bundle (fake Graph transport,
    recording email sender)."""

    settings: Settings
    cipher: TokenCipher
    graph: GraphClient
    email: EmailSender


def build_messaging_services(settings: Settings) -> MessagingServices:
    return MessagingServices(
        settings=settings,
        cipher=TokenCipher.from_setting(settings.token_encryption_key),
        graph=GraphClient(settings.meta_graph_base_url, settings.meta_graph_api_version),
        email=SmtpEmailSender(
            SmtpSettings(
                host=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=settings.smtp_password,
                starttls=settings.smtp_starttls,
                sender=settings.email_from,
            )
        ),
    )


def connections(session: Session, product: Product) -> SqlAlchemyConnectionRepository:
    return SqlAlchemyConnectionRepository(session, product)


def sender_for(services: MessagingServices, queue: SqlAlchemyJobQueue) -> SenderFor:
    """Each connection says how it sends: the Cloud API, or the log sender (development)."""

    def choose(connection: WhatsAppConnection) -> WhatsAppSender:
        if connection.sender is SenderKind.CLOUD:
            return CloudApiSender(services.graph, services.cipher)
        return LogSender(queue)

    return choose


def graph_for(services: MessagingServices) -> Callable[[WhatsAppConnection], GraphPort]:
    def choose(connection: WhatsAppConnection) -> GraphPort:
        if connection.sender is SenderKind.CLOUD:
            return CloudGraphPort(services.graph, services.cipher)
        return LogGraphPort()

    return choose


def connection_defaults(settings: Settings) -> ConnectionDefaults:
    return ConnectionDefaults(
        sender=SenderKind(settings.whatsapp_sender),
        template_name=settings.whatsapp_default_template,
        template_language=settings.whatsapp_default_template_language,
    )


def connection_health(
    session: Session, product: Product, clock: Clock = utc_now
) -> ConnectionHealth:
    return ConnectionHealth(
        connections(session, product),
        SqlAlchemyOutboundRepository(session),
        SqlAlchemyJobQueue(session, clock, product),
        SqlAlchemyAuditLog(session),
        clock,
    )


def ingest_webhook(
    session: Session,
    services: MessagingServices,
    product: Product,
    template_updates: TemplateUpdates | None = None,
) -> IngestWebhook:
    repository = connections(session, product)
    return IngestWebhook(
        repository,
        SqlAlchemyInboundEventRepository(session),
        ApplyDeliveryStatus(SqlAlchemyOutboundRepository(session)),
        SqlAlchemyJobQueue(session, queue=product),
        timedelta(seconds=services.settings.inbound_debounce_seconds),
        account_updates=ApplyAccountUpdate(
            repository, connection_health(session, product), SqlAlchemyAuditLog(session)
        ),
        template_updates=template_updates,
    )


def webhook_secrets(services: MessagingServices) -> tuple[str, str]:
    """(the product's Meta app secret, its webhook verify token)."""
    return services.settings.meta_app_secret, services.settings.whatsapp_verify_token


def save_connection(
    session: Session, services: MessagingServices, product: Product
) -> SaveConnection:
    return SaveConnection(
        connections(session, product),
        services.cipher.encrypt,
        connection_defaults(services.settings),
        audit=SqlAlchemyAuditLog(session),
        resume=connection_health(session, product),
    )


def manage_connection(
    session: Session, services: MessagingServices, product: Product
) -> ManageConnection:
    return ManageConnection(
        connections(session, product),
        graph_for(services),
        sender_for(services, SqlAlchemyJobQueue(session, queue=product)),
        audit=SqlAlchemyAuditLog(session),
        resume=connection_health(session, product),
    )


def embedded_signup(
    session: Session, services: MessagingServices, product: Product
) -> CompleteEmbeddedSignup:
    settings = services.settings
    return CompleteEmbeddedSignup(
        SqlAlchemySignupRepository(session),
        connections(session, product),
        CloudSignupGraph(services.graph, settings.meta_app_id, settings.meta_app_secret),
        services.cipher,
        connection_defaults(settings),
        connection_health(session, product),
        SqlAlchemyAuditLog(session),
    )


def signup_state(session: Session) -> Callable[[UUID], Signup | None]:
    return SqlAlchemySignupRepository(session).get


def tenant_is_active(session: Session) -> Callable[[UUID], bool]:
    """False for a suspended business: no replies, emails or scheduled checks."""

    def active(tenant_id: UUID) -> bool:
        model = session.get(TenantModel, tenant_id)
        return model is None or model.status != TenantStatus.SUSPENDED.value

    return active


def owner_emails(session: Session) -> Callable[[UUID], Sequence[str]]:
    def owners(tenant_id: UUID) -> Sequence[str]:
        return list(
            session.scalars(
                select(ProfileModel.email)
                .where(ProfileModel.tenant_id == tenant_id, ProfileModel.role == "owner")
                .order_by(ProfileModel.email)
            )
        )

    return owners


def business_name(session: Session) -> Callable[[UUID], str]:
    def name(tenant_id: UUID) -> str:
        model = session.get(TenantModel, tenant_id)
        return model.name if model else ""

    return name


def reconnect_link(session: Session, product: Product) -> Callable[[UUID, UUID], int]:
    return RequestReconnectLink(
        owner_emails(session),
        SqlAlchemyJobQueue(session, queue=product),
        SqlAlchemyAuditLog(session),
        utc_now,
    )


def whatsapp_job_handlers(
    session: Session,
    services: MessagingServices,
    product: Product,
    *,
    product_name: str,
    stopped: str,
    clock: Clock = utc_now,
) -> list[tuple[str, JobHandler]]:
    """Sending, read receipts, the 6-hourly health sweep and checks, the reconnect email and
    the log sender's simulated statuses. The process job (what an inbound message does) is
    the product's own."""
    settings = services.settings
    queue = SqlAlchemyJobQueue(session, clock, product)
    repository = connections(session, product)
    outbound = SqlAlchemyOutboundRepository(session)
    choose_sender = sender_for(services, queue)
    health = connection_health(session, product, clock)
    is_active = tenant_is_active(session)
    statuses = ApplyDeliveryStatus(outbound)

    def log_status(job: Job) -> None:
        """The log sender's simulated sent / delivered / read, through Meta's code path."""
        statuses.execute(job.payload["wamid"], job.payload["status"], clock())

    return [
        (SEND_JOB, SendQueued(outbound, repository, choose_sender, clock, health, is_active)),
        (MARK_READ_JOB, MarkRead(repository, choose_sender, health)),
        (HEALTH_SWEEP_JOB, HealthSweep(repository, queue, is_active, clock)),
        (HEALTH_CHECK_JOB, HealthCheck(repository, graph_for(services), health, is_active, clock)),
        (
            RECONNECT_EMAIL_JOB,
            SendReconnectEmail(
                owner_emails(session),
                business_name(session),
                services.email,
                settings.panel_url,
                is_active,
                product_name=product_name,
                stopped=stopped,
            ),
        ),
        (LOG_STATUS_JOB, log_status),
    ]
