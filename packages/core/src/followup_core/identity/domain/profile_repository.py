from typing import Protocol
from uuid import UUID

from .profile import Profile


class ProfileRepository(Protocol):
    def get_by_id(self, user_id: UUID) -> Profile | None: ...

    def get_by_email(self, email: str) -> Profile | None: ...

    def add(self, profile: Profile) -> None: ...

    def set_platform_admin(self, user_id: UUID, value: bool) -> None: ...
