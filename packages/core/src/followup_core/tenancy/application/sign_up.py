import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from followup_core.identity.domain.profile import Profile, Role
from followup_core.identity.domain.profile_repository import ProfileRepository

from ..domain.audit import ActorKind, AuditAction, AuditEvent, AuditLog, NoAuditLog
from ..domain.business_settings import BusinessSettings, BusinessType
from ..domain.business_settings_repository import BusinessSettingsRepository
from ..domain.errors import TenantNotFoundError
from ..domain.onboarding import Onboarding
from ..domain.onboarding_repository import OnboardingRepository
from ..domain.owner_claims import OwnerClaimRepository
from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository
from .defaults import SetupDefaults

logger = logging.getLogger("followup.tenancy")


def _not_confirmed() -> bool:
    return False


@dataclass(frozen=True, slots=True)
class SignUpResult:
    profile: Profile
    tenant: Tenant
    created: bool


class SignUp:
    def __init__(
        self,
        tenant_repository: TenantRepository,
        profile_repository: ProfileRepository,
        onboarding_repository: OnboardingRepository,
        settings_repository: BusinessSettingsRepository,
        defaults: SetupDefaults,
        claims: OwnerClaimRepository | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._tenant_repository = tenant_repository
        self._profile_repository = profile_repository
        self._onboarding_repository = onboarding_repository
        self._settings_repository = settings_repository
        self._defaults = defaults
        self._claims = claims
        self._audit = audit or NoAuditLog()

    def execute(
        self,
        user_id: UUID,
        email: str,
        business_name: str,
        business_type: str,
        email_confirmed: Callable[[], bool] = _not_confirmed,
    ) -> SignUpResult:
        """`email_confirmed` is asked only when an admin created a business for this email:
        joining it needs a proven email. Without proof, sign-up creates a new business as
        usual and the claim stays open."""
        existing_profile = self._profile_repository.get_by_id(user_id)
        if existing_profile is not None:
            tenant = self._tenant_repository.get_by_id(existing_profile.tenant_id)
            if tenant is None:
                raise TenantNotFoundError("The profile's tenant does not exist.")
            return SignUpResult(
                profile=existing_profile,
                tenant=tenant,
                created=False,
            )

        claim = self._claims.get_open(email) if self._claims is not None else None
        if claim is not None:
            if email_confirmed():
                return self._claim(user_id, email, claim.tenant_id)
            logger.warning("owner_claim_skipped_unconfirmed_email", extra={"user_id": str(user_id)})

        parsed_type = BusinessType.parse(business_type)
        tenant = self._with_free_slug(Tenant.create(business_name))

        profile = Profile(
            id=user_id,
            email=email,
            display_name=email,
            tenant_id=tenant.id,
            role=Role.OWNER,
            is_platform_admin=False,
        )

        self._tenant_repository.add(tenant)
        self._profile_repository.add(profile)
        self._settings_repository.add(
            BusinessSettings(
                tenant_id=tenant.id,
                business_type=parsed_type,
                timezone=self._defaults.timezone,
                team_hours=self._defaults.team_hours,
                notification_emails=(profile.email,),
            )
        )
        now = datetime.now(UTC)
        self._onboarding_repository.add(Onboarding.start(tenant.id, now))
        self._audit.record(
            AuditEvent(
                tenant.id, now, ActorKind.USER, AuditAction.SIGN_UP, actor_profile_id=user_id
            )
        )
        return SignUpResult(profile=profile, tenant=tenant, created=True)

    def _claim(self, user_id: UUID, email: str, tenant_id: UUID) -> SignUpResult:
        """An admin created this business for this email ("Dar de alta"): the owner joins
        it instead of creating another one. The business name typed at sign-up is ignored."""
        tenant = self._tenant_repository.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError("The claimed tenant does not exist.")
        profile = Profile(
            id=user_id,
            email=email,
            display_name=email,
            tenant_id=tenant.id,
            role=Role.OWNER,
            is_platform_admin=False,
        )
        self._profile_repository.add(profile)
        now = datetime.now(UTC)
        assert self._claims is not None
        self._claims.mark_claimed(email, now)
        self._audit.record(
            AuditEvent(
                tenant.id, now, ActorKind.USER, AuditAction.OWNER_CLAIMED, actor_profile_id=user_id
            )
        )
        return SignUpResult(profile=profile, tenant=tenant, created=True)

    def _with_free_slug(self, tenant: Tenant) -> Tenant:
        slug = tenant.slug
        suffix = 2
        while self._tenant_repository.slug_exists(slug):
            slug = f"{tenant.slug}-{suffix}"
            suffix += 1
        return replace(tenant, slug=slug)
