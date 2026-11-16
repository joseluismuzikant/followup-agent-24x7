"""Cuentas Claras's composition root: every use case built with its adapters. Core's
adapters always get this product's key (a tenant, profile or job of another product does
not exist here)."""

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from followup_core.identity.application.accounts import (
    InviteOwner,
    ResendInvitation,
    ResetTemporaryPassword,
)
from followup_core.identity.domain.account import AccountDirectory
from followup_core.identity.domain.token_verifier import TokenVerifier
from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository
from followup_core.messaging.application.connections import ManageConnection, SaveConnection
from followup_core.messaging.application.pipeline import IngestWebhook
from followup_core.messaging.application.signup import CompleteEmbeddedSignup
from followup_core.messaging.domain.signup import Signup
from followup_core.messaging.infrastructure.repositories import SqlAlchemyWebhookCounters
from followup_core.scheduling.domain.jobs import NewJob
from followup_core.scheduling.infrastructure.queue import SqlAlchemyJobQueue
from followup_core.tenancy.application.admin_tenants import (
    CreateBusinessForOwner,
    SetTenantSuspension,
)
from followup_core.tenancy.application.defaults import BusinessSettingsDefaults
from followup_core.tenancy.application.get_setup_checklist import GetSetupChecklist
from followup_core.tenancy.application.get_tenant import GetTenant
from followup_core.tenancy.application.onboarding_flow import AdvanceOnboarding, GetOnboarding
from followup_core.tenancy.application.setup_facts import FactProvider, always, not_yet
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.application.tenant_settings import (
    GetTenantSettings,
    UpdateTenantSettings,
)
from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog
from followup_core.tenancy.domain.business_settings import (
    DEFAULT_TIMEZONE,
    TEAM_HOURS_WEEKDAYS_9_18,
    ScheduleBlock,
)
from followup_core.tenancy.domain.tenant import TenantStatus
from followup_core.tenancy.infrastructure.audit_repository import (
    SqlAlchemyAuditLog,
    SqlAlchemyOwnerClaimRepository,
)
from followup_core.tenancy.infrastructure.models import TenantModel
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository
from followup_core.tenancy.infrastructure.setup_repositories import (
    SqlAlchemyBusinessSettingsRepository,
    SqlAlchemyOnboardingRepository,
)
from followup_platform import invitations
from followup_platform.identity import build_account_directory, build_token_verifier
from followup_platform.whatsapp import wiring
from followup_platform.whatsapp.wiring import MessagingServices
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import CuentasAction
from .backoffice.infrastructure.queries import SqlAlchemyCuentasBackofficeQueries
from .clients.application.clients import CreateClient, GetClient, ListClients, UpdateClient
from .clients.infrastructure.repository import SqlAlchemyClientRepository
from .config import get_settings
from .database import get_session
from .invoices.application.imports import GetImportErrors, ImportInvoices
from .invoices.application.invoices import (
    CancelInvoice,
    CreateInvoice,
    GetInvoice,
    GetSummary,
    ListInvoices,
    MarkInvoicePaid,
    PromiseInvoice,
    RemovePromise,
    UpdateInvoice,
)
from .invoices.domain.invoice import Invoice
from .invoices.infrastructure.imports import (
    SqlAlchemyInvoiceImportRepository,
    read_invoice_table,
)
from .invoices.infrastructure.repository import SqlAlchemyInvoiceRepository
from .payments.application.payments import GetPaymentPage, SaveTransferDetails
from .payments.infrastructure.repository import (
    SqlAlchemyPaymentRequestRepository,
    SqlAlchemyPaymentSettingsRepository,
)
from .product import DEFINITION, PRODUCT
from .reminders.application.context import LoadContext
from .reminders.application.next_actions import DescribeNextActions
from .reminders.application.planner import PlanReminders, plan_now
from .reminders.application.settings import GetReminderSettings, SaveReminderPolicy
from .reminders.application.templates import (
    SYNC_TEMPLATES_JOB,
    ApplyTemplateStatus,
    SaveTemplateText,
)
from .reminders.domain.events import Outcome, ReminderEvent
from .reminders.domain.next_action import NextAction
from .reminders.infrastructure.holidays import argentine_holidays
from .reminders.infrastructure.repositories import (
    SqlAlchemyOwedInvoices,
    SqlAlchemyReminderLog,
    SqlAlchemyReminderPolicyRepository,
    SqlAlchemyTemplateRepository,
)
from .whatsapp import CuentasWebhookCounters, SaveConnectionWithTemplates, SignupWithTemplates

SessionDep = Annotated[Session, Depends(get_session)]


def utc_now() -> datetime:
    return datetime.now(UTC)


def get_clock() -> Callable[[], datetime]:
    """Now. Statuses ("Vencida", "Por vencer") depend on it; tests pin it."""
    return utc_now


ClockDep = Annotated[Callable[[], datetime], Depends(get_clock)]

# A new business starts with weekday office hours in Buenos Aires: the reminders' send
# window from Day 9.
DEFAULTS = BusinessSettingsDefaults(team_hours=TEAM_HOURS_WEEKDAYS_9_18, timezone=DEFAULT_TIMEZONE)


@lru_cache
def get_token_verifier() -> TokenVerifier:
    return build_token_verifier(get_settings())


def get_account_directory(session: SessionDep) -> AccountDirectory:
    """Where passwords live: Supabase Auth, or the local table in AUTH_MODE=dev."""
    return build_account_directory(get_settings(), session)


AccountDirectoryDep = Annotated[AccountDirectory, Depends(get_account_directory)]


def tenants(session: Session) -> SqlAlchemyTenantRepository:
    return SqlAlchemyTenantRepository(session, PRODUCT)


def timezone_of(session: Session) -> Callable[[UUID], str]:
    settings = SqlAlchemyBusinessSettingsRepository(session)

    def timezone(tenant_id: UUID) -> str:
        found = settings.get(tenant_id)
        return found.timezone if found is not None else DEFAULT_TIMEZONE

    return timezone


def get_timezone_of(session: SessionDep) -> Callable[[UUID], str]:
    return timezone_of(session)


# --- tenancy ---------------------------------------------------------------------------------


def sign_up_use_case(session: SessionDep) -> SignUp:
    return SignUp(
        SqlAlchemyProfileRepository(session, PRODUCT),
        tenants(session),
        SqlAlchemyOwnerClaimRepository(session, PRODUCT),
        SqlAlchemyAuditLog(session),
        definition=DEFINITION,
    )


def get_tenant_use_case(session: SessionDep) -> GetTenant:
    return GetTenant(tenants(session))


def fact_providers(session: Session) -> dict[str, FactProvider]:
    """Cuentas Claras's setup facts (product.FACTS). Mercado Pago arrives on Day 9B."""

    def whatsapp_connected(tenant_id: UUID) -> bool:
        connection = wiring.connections(session, PRODUCT).get_by_tenant(tenant_id)
        return connection is not None and connection.is_connected

    return {
        "account_created": always,
        "invoices_loaded": SqlAlchemyInvoiceRepository(session).has_any,
        "whatsapp_connected": whatsapp_connected,
        "mercado_pago_connected": not_yet,
        "reminders_configured": SqlAlchemyReminderPolicyRepository(session).is_configured,
    }


def setup_checklist(session: Session) -> GetSetupChecklist:
    return GetSetupChecklist(DEFINITION.checklist, fact_providers(session))


def setup_checklist_dependency(session: SessionDep) -> GetSetupChecklist:
    return setup_checklist(session)


def get_onboarding_use_case(session: SessionDep) -> GetOnboarding:
    return GetOnboarding(SqlAlchemyOnboardingRepository(session), setup_checklist(session))


def advance_onboarding_use_case(session: SessionDep) -> AdvanceOnboarding:
    return AdvanceOnboarding(
        SqlAlchemyOnboardingRepository(session),
        setup_checklist(session),
        DEFINITION.onboarding_steps,
    )


def get_tenant_settings_use_case(session: SessionDep) -> GetTenantSettings:
    return GetTenantSettings(tenants(session), SqlAlchemyBusinessSettingsRepository(session))


def update_tenant_settings_use_case(session: SessionDep) -> UpdateTenantSettings:
    return UpdateTenantSettings(tenants(session), SqlAlchemyBusinessSettingsRepository(session))


# --- clients and invoices --------------------------------------------------------------------


def create_client_use_case(session: SessionDep, clock: ClockDep) -> CreateClient:
    return CreateClient(SqlAlchemyClientRepository(session), SqlAlchemyAuditLog(session), clock)


def update_client_use_case(session: SessionDep, clock: ClockDep) -> UpdateClient:
    return UpdateClient(SqlAlchemyClientRepository(session), SqlAlchemyAuditLog(session), clock)


def list_clients_use_case(session: SessionDep) -> ListClients:
    return ListClients(SqlAlchemyClientRepository(session))


def get_client_use_case(session: SessionDep) -> GetClient:
    return GetClient(SqlAlchemyClientRepository(session))


def client_invoices(session: SessionDep) -> SqlAlchemyInvoiceRepository:
    return SqlAlchemyInvoiceRepository(session)


def list_invoices_use_case(session: SessionDep, clock: ClockDep) -> ListInvoices:
    return ListInvoices(SqlAlchemyInvoiceRepository(session), timezone_of(session), clock)


def summary_use_case(session: SessionDep, clock: ClockDep) -> GetSummary:
    return GetSummary(SqlAlchemyInvoiceRepository(session), timezone_of(session), clock)


def _invoice_args(session: Session, clock: Callable[[], datetime]):  # noqa: ANN202
    return (
        SqlAlchemyInvoiceRepository(session),
        SqlAlchemyClientRepository(session),
        SqlAlchemyAuditLog(session),
        timezone_of(session),
        clock,
    )


def get_invoice_use_case(session: SessionDep, clock: ClockDep) -> GetInvoice:
    return GetInvoice(*_invoice_args(session, clock))


def create_invoice_use_case(session: SessionDep, clock: ClockDep) -> CreateInvoice:
    return CreateInvoice(*_invoice_args(session, clock))


def update_invoice_use_case(session: SessionDep, clock: ClockDep) -> UpdateInvoice:
    return UpdateInvoice(*_invoice_args(session, clock))


def mark_paid_use_case(session: SessionDep, clock: ClockDep) -> MarkInvoicePaid:
    return MarkInvoicePaid(*_invoice_args(session, clock))


def cancel_invoice_use_case(session: SessionDep, clock: ClockDep) -> CancelInvoice:
    return CancelInvoice(*_invoice_args(session, clock))


def import_invoices_use_case(session: SessionDep, clock: ClockDep) -> ImportInvoices:
    return ImportInvoices(
        SqlAlchemyClientRepository(session),
        SqlAlchemyInvoiceRepository(session),
        SqlAlchemyInvoiceImportRepository(session),
        read_invoice_table,
        SqlAlchemyAuditLog(session),
        timezone_of(session),
        clock,
    )


def import_errors_use_case(session: SessionDep) -> GetImportErrors:
    return GetImportErrors(SqlAlchemyInvoiceImportRepository(session))


def promise_use_case(session: SessionDep, clock: ClockDep) -> PromiseInvoice:
    return PromiseInvoice(*_invoice_args(session, clock))


def remove_promise_use_case(session: SessionDep, clock: ClockDep) -> RemovePromise:
    return RemovePromise(*_invoice_args(session, clock))


# --- WhatsApp (followup_platform.whatsapp, with this product's key and Meta app) ----------


@lru_cache
def get_messaging_services() -> MessagingServices:
    return wiring.build_messaging_services(get_settings())


ServicesDep = Annotated[MessagingServices, Depends(get_messaging_services)]


def queue_of(session: Session, clock: Callable[[], datetime] = utc_now) -> SqlAlchemyJobQueue:
    return SqlAlchemyJobQueue(session, clock, PRODUCT)


def ingest_webhook_use_case(session: SessionDep, services: ServicesDep) -> IngestWebhook:
    return wiring.ingest_webhook(
        session, services, PRODUCT, ApplyTemplateStatus(SqlAlchemyTemplateRepository(session))
    )


def webhook_counters(session: SessionDep) -> CuentasWebhookCounters:
    return CuentasWebhookCounters(SqlAlchemyWebhookCounters(session))


def get_webhook_secrets(services: ServicesDep) -> tuple[str, str]:
    """(CUENTAS_CLARAS_META_APP_SECRET, CUENTAS_CLARAS_WHATSAPP_VERIFY_TOKEN)."""
    return wiring.webhook_secrets(services)


def save_connection_use_case(session: SessionDep, services: ServicesDep) -> SaveConnection:
    return SaveConnectionWithTemplates(
        wiring.save_connection(session, services, PRODUCT), queue_of(session)
    )


def manage_connection_use_case(session: SessionDep, services: ServicesDep) -> ManageConnection:
    return wiring.manage_connection(session, services, PRODUCT)


def embedded_signup_use_case(session: SessionDep, services: ServicesDep) -> CompleteEmbeddedSignup:
    return SignupWithTemplates(
        wiring.embedded_signup(session, services, PRODUCT), queue_of(session)
    )


def signup_state(session: SessionDep) -> Callable[[UUID], Signup | None]:
    return wiring.signup_state(session)


def audit_log(session: SessionDep) -> AuditLog:
    return SqlAlchemyAuditLog(session)


def reconnect_link_use_case(session: SessionDep) -> Callable[[UUID, UUID], int]:
    return wiring.reconnect_link(session, PRODUCT)


# --- reminders and payments ------------------------------------------------------------------


def schedule_of(session: Session) -> Callable[[UUID], tuple[str, tuple[ScheduleBlock, ...]]]:
    settings = SqlAlchemyBusinessSettingsRepository(session)

    def schedule(tenant_id: UUID) -> tuple[str, tuple[ScheduleBlock, ...]]:
        found = settings.get(tenant_id)
        if found is None:
            return DEFAULT_TIMEZONE, TEAM_HOURS_WEEKDAYS_9_18
        return found.timezone, found.team_hours

    return schedule


def notification_recipients(session: Session) -> Callable[[UUID], Sequence[str]]:
    """Configuración's notification emails, or the owners when there are none."""
    settings = SqlAlchemyBusinessSettingsRepository(session)
    owners = wiring.owner_emails(session)

    def recipients(tenant_id: UUID) -> Sequence[str]:
        found = settings.get(tenant_id)
        if found is not None and found.notification_emails:
            return list(found.notification_emails)
        return owners(tenant_id)

    return recipients


def load_context(session: Session, clock: Callable[[], datetime] = utc_now) -> LoadContext:
    return LoadContext(
        SqlAlchemyReminderPolicyRepository(session),
        SqlAlchemyTemplateRepository(session),
        schedule_of(session),
        argentine_holidays,
        wiring.connections(session, PRODUCT),
        wiring.business_name(session),
        clock,
    )


def plan_reminders(session: Session, clock: Callable[[], datetime] = utc_now) -> PlanReminders:
    return PlanReminders(
        load_context(session, clock),
        SqlAlchemyOwedInvoices(session),
        SqlAlchemyReminderLog(session),
        queue_of(session, clock),
        SqlAlchemyAuditLog(session),
        wiring.tenant_is_active(session),
        clock,
    )


def plan_reminders_use_case(session: SessionDep, clock: ClockDep) -> PlanReminders:
    return plan_reminders(session, clock)


def request_plan(session: SessionDep, clock: ClockDep) -> Callable[[UUID], bool]:
    """Plans the business again (a job, at most one per minute)."""
    queue = queue_of(session, clock)
    return lambda tenant_id: plan_now(queue, tenant_id, clock())


def next_actions(
    session: SessionDep, clock: ClockDep
) -> Callable[[UUID, Sequence[Invoice]], Mapping[UUID, NextAction]]:
    return DescribeNextActions(
        load_context(session, clock),
        SqlAlchemyOwedInvoices(session),
        SqlAlchemyReminderLog(session),
        clock,
    ).execute


def reminder_settings_use_case(session: SessionDep, clock: ClockDep) -> GetReminderSettings:
    return GetReminderSettings(
        load_context(session, clock),
        SqlAlchemyReminderPolicyRepository(session),
        SqlAlchemyReminderLog(session),
        clock,
    )


def save_policy_use_case(session: SessionDep, clock: ClockDep) -> SaveReminderPolicy:
    return SaveReminderPolicy(
        SqlAlchemyReminderPolicyRepository(session),
        queue_of(session, clock),
        SqlAlchemyAuditLog(session),
        clock,
    )


def save_template_use_case(session: SessionDep, clock: ClockDep) -> SaveTemplateText:
    return SaveTemplateText(
        SqlAlchemyTemplateRepository(session),
        queue_of(session, clock),
        SqlAlchemyAuditLog(session),
        clock,
    )


def reminder_events(
    session: SessionDep,
) -> Callable[[UUID, list[Outcome], int], list[ReminderEvent]]:
    return SqlAlchemyReminderLog(session).events_for


def request_template_sync(session: SessionDep, clock: ClockDep) -> Callable[[UUID], bool]:
    queue = queue_of(session, clock)

    def request(tenant_id: UUID) -> bool:
        now = clock()
        return queue.enqueue(
            NewJob(
                SYNC_TEMPLATES_JOB,
                {"tenant_id": str(tenant_id)},
                dedupe_key=f"templates-sync:{tenant_id}:{now:%Y%m%d%H%M}",
                max_attempts=3,
            )
        )

    return request


def admin_plan_audit(session: SessionDep, clock: ClockDep) -> Callable[[UUID, UUID], None]:
    audit = SqlAlchemyAuditLog(session)

    def record(tenant_id: UUID, admin_id: UUID) -> None:
        audit.record(
            AuditEvent(
                tenant_id,
                clock(),
                ActorKind.ADMIN,
                CuentasAction.REMINDERS_PLANNED_BY_ADMIN,
                {},
                actor_profile_id=admin_id,
            )
        )

    return record


def payment_page_use_case(session: SessionDep, clock: ClockDep) -> GetPaymentPage:
    return GetPaymentPage(
        SqlAlchemyPaymentRequestRepository(session),
        SqlAlchemyPaymentSettingsRepository(session),
        SqlAlchemyOwedInvoices(session),
        wiring.business_name(session),
        wiring.tenant_is_active(session),
        clock,
    )


def payment_settings(session: SessionDep) -> SqlAlchemyPaymentSettingsRepository:
    return SqlAlchemyPaymentSettingsRepository(session)


def save_transfer_use_case(session: SessionDep, clock: ClockDep) -> SaveTransferDetails:
    return SaveTransferDetails(
        SqlAlchemyPaymentSettingsRepository(session), SqlAlchemyAuditLog(session), clock
    )


def active_tenants(session: Session) -> Callable[[], list[UUID]]:
    def ids() -> list[UUID]:
        return list(
            session.scalars(
                select(TenantModel.id).where(
                    TenantModel.product == PRODUCT.value,
                    TenantModel.status != TenantStatus.SUSPENDED.value,
                )
            )
        )

    return ids


# --- backoffice ------------------------------------------------------------------------------


def backoffice_queries(session: SessionDep) -> SqlAlchemyCuentasBackofficeQueries:
    return SqlAlchemyCuentasBackofficeQueries(session)


def create_business_use_case(session: SessionDep) -> CreateBusinessForOwner:
    return CreateBusinessForOwner(
        tenants(session),
        SqlAlchemyProfileRepository(session, PRODUCT),
        SqlAlchemyOnboardingRepository(session),
        SqlAlchemyBusinessSettingsRepository(session),
        SqlAlchemyOwnerClaimRepository(session, PRODUCT),
        DEFAULTS,
        SqlAlchemyAuditLog(session),
        definition=DEFINITION,
    )


def invite_owner_use_case(session: SessionDep, directory: AccountDirectoryDep) -> InviteOwner:
    return invitations.invite_owner(session, PRODUCT, directory)


def resend_invitation_use_case(session: SessionDep) -> ResendInvitation:
    return invitations.resend_invitation(session, PRODUCT)


def reset_temporary_password_use_case(
    session: SessionDep, directory: AccountDirectoryDep
) -> ResetTemporaryPassword:
    return invitations.reset_temporary_password(session, PRODUCT, directory)


def tenant_suspension_use_case(session: SessionDep) -> SetTenantSuspension:
    return SetTenantSuspension(tenants(session), SqlAlchemyAuditLog(session))
