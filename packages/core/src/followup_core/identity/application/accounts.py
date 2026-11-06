"""Invitation-only accounts. An admin's "Dar de alta" creates the business, then InviteOwner
creates the owner's account (a temporary password the admin sees once) and emails a link.
Either way in, the person chooses their own password before anything else."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from followup_core.scheduling.domain.jobs import JobQueue, NewJob
from followup_core.tenancy.domain.audit import ActorKind, AuditAction, AuditEvent, AuditLog
from followup_core.tenancy.domain.owner_claims import OwnerClaim, OwnerClaimRepository
from followup_core.tenancy.domain.product import Product
from followup_core.tenancy.domain.tenant import Tenant

from ..domain.account import (
    Account,
    AccountDirectory,
    AccountRepository,
    check_password,
    temporary_password,
)
from ..domain.errors import (
    AccountNotFoundError,
    InvitationExpiredError,
    InvitationNotFoundError,
    InvitationUsedError,
    OwnerAlreadyJoinedError,
)
from ..domain.invitation import Invitation, InvitationRepository, InvitationStatus, new_token

Clock = Callable[[], datetime]
INVITATION_EMAIL_JOB = "identity.invitation_email"


def _now() -> datetime:
    return datetime.now(UTC)


class TenantLookup(Protocol):
    def get_by_id(self, tenant_id: UUID) -> Tenant | None: ...


@dataclass(frozen=True, slots=True)
class InviteResult:
    # Shown once to the admin; None when the person already had an account (their own
    # password from the other product stays).
    temporary_password: str | None
    # The link's token: only the email carries it (the seed prints it for local testing).
    token: str


@dataclass(frozen=True, slots=True)
class InvitationView:
    email: str
    business_name: str
    status: InvitationStatus
    # False when the person already has a password (an account in the other product).
    needs_password: bool


class _Invitations:
    """What inviting and resending share: a new token (older ones stop working), the email
    job and the audit event."""

    def __init__(
        self,
        product: Product,
        invitations: InvitationRepository,
        queue: JobQueue,
        audit: AuditLog,
        clock: Clock,
    ) -> None:
        self._product = product
        self._invitations = invitations
        self._queue = queue
        self._audit = audit
        self._clock = clock

    def send(self, admin_id: UUID, claim: OwnerClaim, action: AuditAction, source: str) -> str:
        now = self._clock()
        token = new_token()
        invitation = Invitation.create(self._product, claim.email, claim.tenant_id, token, now)
        self._invitations.add(invitation)
        self._queue.enqueue(
            NewJob(
                INVITATION_EMAIL_JOB,
                {"invitation_id": str(invitation.id), "token": token},
                dedupe_key=f"invitation:{invitation.id}",
                max_attempts=5,
            )
        )
        self._audit.record(
            AuditEvent(
                claim.tenant_id,
                now,
                ActorKind.ADMIN,
                action,
                {"source": source},
                actor_profile_id=admin_id,
            )
        )
        return token


def _open_claim(claims: OwnerClaimRepository, tenant_id: UUID) -> OwnerClaim:
    claim = claims.get_for_tenant(tenant_id)
    if claim is None:
        raise AccountNotFoundError(str(tenant_id))
    if claim.claimed_at is not None:
        raise OwnerAlreadyJoinedError(str(tenant_id))
    return claim


class InviteOwner:
    def __init__(
        self,
        product: Product,
        accounts: AccountRepository,
        directory: AccountDirectory,
        claims: OwnerClaimRepository,
        invitations: InvitationRepository,
        queue: JobQueue,
        audit: AuditLog,
        clock: Clock = _now,
        password_factory: Callable[[], str] = temporary_password,
    ) -> None:
        self._accounts = accounts
        self._directory = directory
        self._claims = claims
        self._invitations = _Invitations(product, invitations, queue, audit, clock)
        self._clock = clock
        self._password_factory = password_factory

    def execute(self, admin_id: UUID, tenant_id: UUID) -> InviteResult:
        """For the business the admin just created (its owner claim names the email)."""
        claim = _open_claim(self._claims, tenant_id)
        password: str | None = None
        if self._accounts.get_by_email(claim.email) is None:
            password = self._password_factory()
            user_id = self._directory.create_user(claim.email, password)
            self._accounts.add(Account(user_id, claim.email, True, self._clock()))
        token = self._invitations.send(
            admin_id,
            claim,
            AuditAction.OWNER_INVITED,
            "new_account" if password else "existing_account",
        )
        return InviteResult(temporary_password=password, token=token)


class ResendInvitation:
    def __init__(
        self,
        product: Product,
        claims: OwnerClaimRepository,
        invitations: InvitationRepository,
        queue: JobQueue,
        audit: AuditLog,
        clock: Clock = _now,
    ) -> None:
        self._claims = claims
        self._invitations = _Invitations(product, invitations, queue, audit, clock)

    def execute(self, admin_id: UUID, tenant_id: UUID) -> str:
        claim = _open_claim(self._claims, tenant_id)
        return self._invitations.send(admin_id, claim, AuditAction.INVITATION_RESENT, "admin")


class ResetTemporaryPassword:
    """A new temporary password while the owner has not chosen theirs. Never for a person
    who already did (that would let an admin take over their account in the other product)."""

    def __init__(
        self,
        accounts: AccountRepository,
        directory: AccountDirectory,
        claims: OwnerClaimRepository,
        audit: AuditLog,
        clock: Clock = _now,
        password_factory: Callable[[], str] = temporary_password,
    ) -> None:
        self._accounts = accounts
        self._directory = directory
        self._claims = claims
        self._audit = audit
        self._clock = clock
        self._password_factory = password_factory

    def execute(self, admin_id: UUID, tenant_id: UUID) -> str:
        claim = _open_claim(self._claims, tenant_id)
        account = self._accounts.get_by_email(claim.email)
        if account is None:
            raise AccountNotFoundError(claim.email)
        if not account.must_change_password:
            raise OwnerAlreadyJoinedError(claim.email)
        password = self._password_factory()
        self._directory.set_password(account.user_id, account.email, password)
        self._audit.record(
            AuditEvent(
                tenant_id,
                self._clock(),
                ActorKind.ADMIN,
                AuditAction.TEMPORARY_PASSWORD_RESET,
                actor_profile_id=admin_id,
            )
        )
        return password


class GetInvitation:
    def __init__(
        self,
        invitations: InvitationRepository,
        accounts: AccountRepository,
        tenants: TenantLookup,
        clock: Clock = _now,
    ) -> None:
        self._invitations = invitations
        self._accounts = accounts
        self._tenants = tenants
        self._clock = clock

    def execute(self, token: str) -> InvitationView:
        invitation = self._invitations.get_by_token(token)
        tenant = self._tenants.get_by_id(invitation.tenant_id) if invitation else None
        if invitation is None or tenant is None:
            raise InvitationNotFoundError()
        account = self._accounts.get_by_email(invitation.email)
        return InvitationView(
            email=invitation.email,
            business_name=tenant.name,
            status=invitation.status(self._clock()),
            needs_password=account is None or account.must_change_password,
        )


class AcceptInvitation:
    """The link's way in: the person chooses their password (no temporary one needed)."""

    def __init__(
        self,
        invitations: InvitationRepository,
        accounts: AccountRepository,
        directory: AccountDirectory,
        audit: AuditLog,
        clock: Clock = _now,
    ) -> None:
        self._invitations = invitations
        self._accounts = accounts
        self._directory = directory
        self._audit = audit
        self._clock = clock

    def execute(self, token: str, password: str) -> str:
        """The invited email (the panel signs in with it and the new password)."""
        now = self._clock()
        invitation = self._invitations.get_by_token(token)
        if invitation is None:
            raise InvitationNotFoundError()
        status = invitation.status(now)
        if status is InvitationStatus.USED:
            raise InvitationUsedError()
        if status is InvitationStatus.EXPIRED:
            raise InvitationExpiredError()
        account = self._accounts.get_by_email(invitation.email)
        if account is None:
            raise AccountNotFoundError(invitation.email)
        if not account.must_change_password:
            # They already have a password: the link only says "entrá con tu clave".
            raise InvitationUsedError()
        check_password(password, account.email)
        self._directory.set_password(account.user_id, account.email, password)
        self._accounts.set_must_change(account.user_id, False, now)
        self._invitations.mark_accepted(invitation.id, now)
        self._audit.record(
            AuditEvent(invitation.tenant_id, now, ActorKind.USER, AuditAction.INVITATION_ACCEPTED)
        )
        return account.email


class ChangePassword:
    """The forced change after a temporary password, and "¿Olvidaste tu clave?"."""

    def __init__(
        self, accounts: AccountRepository, directory: AccountDirectory, clock: Clock = _now
    ) -> None:
        self._accounts = accounts
        self._directory = directory
        self._clock = clock

    def execute(self, user_id: UUID, email: str, password: str) -> None:
        check_password(password, email)
        self._directory.set_password(user_id, email, password)
        now = self._clock()
        if self._accounts.get(user_id) is None:
            self._accounts.add(Account(user_id, email.strip().lower(), False, now, now))
        else:
            self._accounts.set_must_change(user_id, False, now)
