from typing import Protocol
from uuid import UUID

from .profile import Profile


class ProfileRepository(Protocol):
    """One product's profiles."""

    def get_by_id(self, profile_id: UUID) -> Profile | None: ...

    def get_for_user(self, user_id: UUID) -> Profile | None:
        """The signed-in user's profile in this product."""
        ...

    def get_by_email(self, email: str) -> Profile | None: ...

    def new_profile_id(self, user_id: UUID) -> UUID:
        """The id for this user's new profile: the user id itself for their first profile on
        the platform (as before there were two products), a fresh id otherwise."""
        ...

    def add(self, profile: Profile) -> None: ...

    def set_platform_admin(self, profile_id: UUID, value: bool) -> None: ...
