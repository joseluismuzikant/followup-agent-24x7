"""Invitation use cases built with their adapters, the same in every product: each product's
container passes its session, product key and account directory."""

from uuid import UUID

from followup_core.identity.application.accounts import (
    InviteOwner,
    ResendInvitation,
    ResetTemporaryPassword,
)
from followup_core.identity.application.invitation_email import (
    InvitationEmailData,
    SendInvitationEmail,
)
from followup_core.identity.domain.account import AccountDirectory
from followup_core.identity.infrastructure.accounts import (
    SqlAlchemyAccountRepository,
    SqlAlchemyInvitationRepository,
)
from followup_core.notifications.domain.email import EmailSender
from followup_core.scheduling.infrastructure.queue import SqlAlchemyJobQueue
from followup_core.tenancy.domain.product import Product
from followup_core.tenancy.infrastructure.audit_repository import (
    SqlAlchemyAuditLog,
    SqlAlchemyOwnerClaimRepository,
)
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository
from sqlalchemy.orm import Session


def invite_owner(session: Session, product: Product, directory: AccountDirectory) -> InviteOwner:
    return InviteOwner(
        product,
        SqlAlchemyAccountRepository(session),
        directory,
        SqlAlchemyOwnerClaimRepository(session, product),
        SqlAlchemyInvitationRepository(session),
        SqlAlchemyJobQueue(session, queue=product),
        SqlAlchemyAuditLog(session),
    )


def resend_invitation(session: Session, product: Product) -> ResendInvitation:
    return ResendInvitation(
        product,
        SqlAlchemyOwnerClaimRepository(session, product),
        SqlAlchemyInvitationRepository(session),
        SqlAlchemyJobQueue(session, queue=product),
        SqlAlchemyAuditLog(session),
    )


def reset_temporary_password(
    session: Session, product: Product, directory: AccountDirectory
) -> ResetTemporaryPassword:
    return ResetTemporaryPassword(
        SqlAlchemyAccountRepository(session),
        directory,
        SqlAlchemyOwnerClaimRepository(session, product),
        SqlAlchemyAuditLog(session),
    )


def invitation_email_handler(
    session: Session,
    product: Product,
    sender: EmailSender,
    product_name: str,
    panel_url: str,
) -> SendInvitationEmail:
    invitations = SqlAlchemyInvitationRepository(session)
    tenants = SqlAlchemyTenantRepository(session, product)

    def lookup(invitation_id: UUID) -> InvitationEmailData | None:
        invitation = invitations.get(invitation_id)
        if invitation is None or invitation.accepted_at or invitation.revoked_at:
            return None  # replaced by a newer one, or already used: nothing to send
        tenant = tenants.get_by_id(invitation.tenant_id)
        if tenant is None:
            return None
        return InvitationEmailData(email=invitation.email, business_name=tenant.name)

    return SendInvitationEmail(lookup, sender, product_name, panel_url)
