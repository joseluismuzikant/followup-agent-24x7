import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from followup_core.identity.domain.profile import Profile, Role
from followup_core.identity.domain.profile_repository import ProfileRepository

from ..domain.audit import ActorKind, AuditAction, AuditEvent, AuditLog, NoAuditLog
from ..domain.errors import NotInvitedError, TenantNotFoundError
from ..domain.owner_claims import OwnerClaimRepository
from ..domain.product import ProductDefinition
from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository

logger = logging.getLogger("followup.tenancy")


@dataclass(frozen=True, slots=True)
class SignUpResult:
    profile: Profile
    tenant: Tenant
    created: bool


class SignUp:
    """Joins the business an admin created for this email ("Dar de alta"). Sign-up is
    invitation-only: an email without an open claim in this product gets NotInvitedError."""

    def __init__(
        self,
        profile_repository: ProfileRepository,
        tenant_repository: TenantRepository,
        claims: OwnerClaimRepository,
        audit: AuditLog | None = None,
        *,
        definition: ProductDefinition,
    ) -> None:
        self._definition = definition
        self._tenant_repository = tenant_repository
        self._profile_repository = profile_repository
        self._claims = claims
        self._audit = audit or NoAuditLog()

    def execute(self, user_id: UUID, email: str) -> SignUpResult:
        email = email.strip().lower()
        existing_profile = self._profile_repository.get_for_user(user_id)
        if existing_profile is not None:
            tenant = self._tenant_repository.get_by_id(existing_profile.tenant_id)
            if tenant is None:
                raise TenantNotFoundError("The profile's tenant does not exist.")
            return SignUpResult(profile=existing_profile, tenant=tenant, created=False)

        claim = self._claims.get_open(email)
        if claim is None:
            logger.info("sign_up_not_invited", extra={"user_id": str(user_id)})
            raise NotInvitedError(email)
        tenant = self._tenant_repository.get_by_id(claim.tenant_id)
        if tenant is None:
            raise TenantNotFoundError("The claimed tenant does not exist.")
        profile = Profile(
            id=self._profile_repository.new_profile_id(user_id),
            email=email,
            display_name=email,
            tenant_id=tenant.id,
            role=Role.OWNER,
            is_platform_admin=False,
            user_id=user_id,
            product=self._definition.product,
        )
        self._profile_repository.add(profile)
        now = datetime.now(UTC)
        self._claims.mark_claimed(email, now)
        self._audit.record(
            AuditEvent(
                tenant.id,
                now,
                ActorKind.USER,
                AuditAction.OWNER_CLAIMED,
                actor_profile_id=profile.id,
            )
        )
        return SignUpResult(profile=profile, tenant=tenant, created=True)
