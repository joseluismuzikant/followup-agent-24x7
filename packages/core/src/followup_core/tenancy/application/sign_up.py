from dataclasses import dataclass, replace
from uuid import UUID

from followup_core.identity.domain.profile import Profile, Role
from followup_core.identity.domain.profile_repository import ProfileRepository

from ..domain.errors import TenantNotFoundError
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
        return SignUpResult(profile=profile, tenant=tenant, created=True)

    def _with_free_slug(self, tenant: Tenant) -> Tenant:
        slug = tenant.slug
        suffix = 2
        while self._tenant_repository.slug_exists(slug):
            slug = f"{tenant.slug}-{suffix}"
            suffix += 1
        return replace(tenant, slug=slug)
