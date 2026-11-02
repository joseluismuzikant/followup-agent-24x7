from ..domain.errors import ProfileNotFoundError
from ..domain.profile import Profile
from ..domain.profile_repository import ProfileRepository


class SetPlatformAdmin:
    """Grants (or removes) platform administration to an existing profile, found by email.

    Used by operator scripts; there is no endpoint for it.
    """

    def __init__(self, profiles: ProfileRepository) -> None:
        self._profiles = profiles

    def execute(self, email: str, value: bool = True) -> Profile:
        profile = self._profiles.get_by_email(email)
        if profile is None:
            raise ProfileNotFoundError(f"No profile with email '{email}'.")
        if profile.is_platform_admin != value:
            self._profiles.set_platform_admin(profile.id, value)
        updated = self._profiles.get_by_id(profile.id)
        assert updated is not None
        return updated
