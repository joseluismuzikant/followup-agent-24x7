"""Cuentas Claras's composition root: every use case built with its adapters. Core's
adapters always get this product's key (a tenant, profile or job of another product does
not exist here)."""

from collections.abc import Callable
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
from followup_core.tenancy.domain.business_settings import (
    DEFAULT_TIMEZONE,
    TEAM_HOURS_WEEKDAYS_9_18,
)
from followup_core.tenancy.infrastructure.audit_repository import (
    SqlAlchemyAuditLog,
    SqlAlchemyOwnerClaimRepository,
)
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository
from followup_core.tenancy.infrastructure.setup_repositories import (
    SqlAlchemyBusinessSettingsRepository,
    SqlAlchemyOnboardingRepository,
)
from followup_platform import invitations
from followup_platform.identity import build_account_directory, build_token_verifier
from sqlalchemy.orm import Session

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
    UpdateInvoice,
)
from .invoices.infrastructure.imports import (
    SqlAlchemyInvoiceImportRepository,
    read_invoice_table,
)
from .invoices.infrastructure.repository import SqlAlchemyInvoiceRepository
from .product import DEFINITION, PRODUCT

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
    """Cuentas Claras's setup facts (product.FACTS). WhatsApp, Mercado Pago and reminders
    arrive on Day 9."""
    return {
        "account_created": always,
        "invoices_loaded": SqlAlchemyInvoiceRepository(session).has_any,
        "whatsapp_connected": not_yet,
        "mercado_pago_connected": not_yet,
        "reminders_configured": not_yet,
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
