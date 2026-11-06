from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from followup_core.identity.application.set_platform_admin import SetPlatformAdmin
from followup_core.identity.domain.errors import ProfileNotFoundError
from followup_core.identity.domain.profile import Profile, Role


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self.profiles: dict[UUID, Profile] = {}

    def get_by_id(self, profile_id: UUID) -> Profile | None:
        return self.profiles.get(profile_id)

    def get_for_user(self, user_id: UUID) -> Profile | None:
        return next((p for p in self.profiles.values() if p.user_id == user_id), None)

    def new_profile_id(self, user_id: UUID) -> UUID:
        return user_id

    def get_by_email(self, email: str) -> Profile | None:
        return next((p for p in self.profiles.values() if p.email == email.lower()), None)

    def add(self, profile: Profile) -> None:
        self.profiles[profile.id] = profile

    def set_platform_admin(self, profile_id: UUID, value: bool) -> None:
        self.profiles[profile_id] = replace(self.profiles[profile_id], is_platform_admin=value)


def test_grants_platform_admin_by_email() -> None:
    profiles = InMemoryProfileRepository()
    profile = Profile(uuid4(), "admin@local.test", "Admin", uuid4(), Role.OWNER, False)
    profiles.add(profile)

    updated = SetPlatformAdmin(profiles).execute("Admin@Local.test")

    assert updated.is_platform_admin is True
    assert profiles.profiles[profile.id].is_platform_admin is True


def test_unknown_email_is_an_error() -> None:
    with pytest.raises(ProfileNotFoundError):
        SetPlatformAdmin(InMemoryProfileRepository()).execute("nadie@local.test")
