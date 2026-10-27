from dataclasses import dataclass
from uuid import UUID

from followup_core.identity.domain.profile import Profile, Role
from followup_core.identity.domain.profile_repository import ProfileRepository

from ..domain.errors import DuplicateTenantSlugError, TenantNotFoundError
from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository


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
    ) -> None:
        self._tenant_repository = tenant_repository
        self._profile_repository = profile_repository

    def execute(self, user_id: UUID, email: str, business_name: str) -> SignUpResult:
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

        tenant = Tenant.create(business_name)
        if self._tenant_repository.slug_exists(tenant.slug):
            raise DuplicateTenantSlugError(f"Tenant slug '{tenant.slug}' already exists.")

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
        return SignUpResult(profile=profile, tenant=tenant, created=True)
