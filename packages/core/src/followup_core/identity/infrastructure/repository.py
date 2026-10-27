from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from ..domain.profile import Profile, Role
from .models import ProfileModel


def _to_domain(model: ProfileModel) -> Profile:
    return Profile(
        id=model.id,
        email=model.email,
        display_name=model.display_name,
        tenant_id=model.tenant_id,
        role=Role(model.role),
        is_platform_admin=model.is_platform_admin,
    )


class SqlAlchemyProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: UUID) -> Profile | None:
        model = self._session.get(ProfileModel, user_id)
        return _to_domain(model) if model is not None else None

    def add(self, profile: Profile) -> None:
        self._session.add(
            ProfileModel(
                id=profile.id,
                email=profile.email,
                display_name=profile.display_name,
                tenant_id=profile.tenant_id,
                role=profile.role.value,
                is_platform_admin=profile.is_platform_admin,
                created_at=datetime.now(UTC),
            )
        )
