"""Platform admin actions on a business: create one for an owner ("Dar de alta"), suspend
and reactivate."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from followup_core.identity.domain.profile_repository import ProfileRepository

from ..domain.audit import ActorKind, AuditAction, AuditEvent, AuditLog
from ..domain.business_settings import BusinessSettings, BusinessType
from ..domain.business_settings_repository import BusinessSettingsRepository
from ..domain.errors import OwnerEmailTakenError, TenantNotFoundError
from ..domain.onboarding import Onboarding
from ..domain.onboarding_repository import OnboardingRepository
from ..domain.owner_claims import OwnerClaim, OwnerClaimRepository
from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository
from .defaults import SetupDefaults

Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(UTC)


class CreateBusinessForOwner:
    """The same records as a self-serve sign-up (tenant, settings, onboarding), minus the
    profile: the owner gets it when they sign up with this email (SignUp claims it)."""

    def __init__(
        self,
        tenants: TenantRepository,
        profiles: ProfileRepository,
        onboardings: OnboardingRepository,
        settings: BusinessSettingsRepository,
        claims: OwnerClaimRepository,
        defaults: SetupDefaults,
        audit: AuditLog,
        clock: Clock = _now,
    ) -> None:
        self._tenants = tenants
        self._profiles = profiles
        self._onboardings = onboardings
        self._settings = settings
        self._claims = claims
        self._defaults = defaults
        self._audit = audit
        self._clock = clock

    def execute(
        self, admin_id: UUID, business_name: str, business_type: str, owner_email: str
    ) -> Tenant:
        email = owner_email.strip().lower()
        if self._profiles.get_by_email(email) is not None or self._claims.exists(email):
            raise OwnerEmailTakenError(email)
        parsed_type = BusinessType.parse(business_type)
        tenant = Tenant.create(business_name)
        slug, suffix = tenant.slug, 2
        while self._tenants.slug_exists(slug):
            slug = f"{tenant.slug}-{suffix}"
            suffix += 1
        tenant = replace(tenant, slug=slug)
        now = self._clock()
        self._tenants.add(tenant)
        self._settings.add(
            BusinessSettings(
                tenant_id=tenant.id,
                business_type=parsed_type,
                timezone=self._defaults.timezone,
                team_hours=self._defaults.team_hours,
                notification_emails=(email,),
            )
        )
        self._onboardings.add(Onboarding.start(tenant.id, now))
        self._claims.add(OwnerClaim(email, tenant.id, now))
        self._audit.record(
            AuditEvent(
                tenant.id,
                now,
                ActorKind.ADMIN,
                AuditAction.TENANT_CREATED_BY_ADMIN,
                actor_profile_id=admin_id,
            )
        )
        return tenant


class SetTenantSuspension:
    def __init__(self, tenants: TenantRepository, audit: AuditLog, clock: Clock = _now) -> None:
        self._tenants = tenants
        self._audit = audit
        self._clock = clock

    def _require(self, tenant_id: UUID) -> Tenant:
        tenant = self._tenants.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(str(tenant_id))
        return tenant

    def suspend(self, admin_id: UUID, tenant_id: UUID, reason: str) -> Tenant:
        now = self._clock()
        tenant = self._require(tenant_id).suspend(reason, now)
        self._tenants.save(tenant)
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.ADMIN,
                AuditAction.TENANT_SUSPENDED,
                actor_profile_id=admin_id,
            )
        )
        return tenant

    def reactivate(self, admin_id: UUID, tenant_id: UUID) -> Tenant:
        current = self._require(tenant_id)
        if not current.is_suspended:
            return current
        tenant = current.reactivate()
        self._tenants.save(tenant)
        self._audit.record(
            AuditEvent(
                tenant_id,
                self._clock(),
                ActorKind.ADMIN,
                AuditAction.TENANT_REACTIVATED,
                actor_profile_id=admin_id,
            )
        )
        return tenant
