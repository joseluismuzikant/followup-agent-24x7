from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from followup_core.identity.domain.profile import Profile, Role
from followup_core.identity.domain.profile_repository import ProfileRepository

from ..domain.business_settings import BusinessSettings, BusinessType
from ..domain.business_settings_repository import BusinessSettingsRepository
from ..domain.errors import TenantNotFoundError
from ..domain.onboarding import Onboarding
from ..domain.onboarding_repository import OnboardingRepository
from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository
from .defaults import SetupDefaults


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
    ) -> None:
        self._tenant_repository = tenant_repository
        self._profile_repository = profile_repository
        self._onboarding_repository = onboarding_repository
        self._settings_repository = settings_repository
        self._defaults = defaults

    def execute(
        self,
        user_id: UUID,
        email: str,
        business_name: str,
        business_type: str,
    ) -> SignUpResult:
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
        self._onboarding_repository.add(Onboarding.start(tenant.id, datetime.now(UTC)))
        return SignUpResult(profile=profile, tenant=tenant, created=True)

    def _with_free_slug(self, tenant: Tenant) -> Tenant:
        slug = tenant.slug
        suffix = 2
        while self._tenant_repository.slug_exists(slug):
            slug = f"{tenant.slug}-{suffix}"
            suffix += 1
        return replace(tenant, slug=slug)
