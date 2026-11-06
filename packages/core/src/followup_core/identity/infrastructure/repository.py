from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, exists, select, update
from sqlalchemy.orm import Session

from followup_core.tenancy.domain.product import FIRST_PRODUCT, Product

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
        user_id=model.user_id,
        product=Product(model.product),
    )


class SqlAlchemyProfileRepository:
    """Profiles of one product; another product's profile of the same person is not here."""

    def __init__(self, session: Session, product: Product = FIRST_PRODUCT) -> None:
        self._session = session
        self._product = product

    def _one(self, *conditions: ColumnElement[bool]) -> Profile | None:
        model = self._session.scalar(
            select(ProfileModel).where(ProfileModel.product == self._product, *conditions)
        )
        return _to_domain(model) if model is not None else None

    def get_by_id(self, profile_id: UUID) -> Profile | None:
        return self._one(ProfileModel.id == profile_id)

    def get_for_user(self, user_id: UUID) -> Profile | None:
        return self._one(ProfileModel.user_id == user_id)

    def get_by_email(self, email: str) -> Profile | None:
        return self._one(ProfileModel.email == email.strip().lower())

    def new_profile_id(self, user_id: UUID) -> UUID:
        taken = self._session.scalar(
            select(exists().where((ProfileModel.user_id == user_id) | (ProfileModel.id == user_id)))
        )
        return uuid4() if taken else user_id

    def set_platform_admin(self, profile_id: UUID, value: bool) -> None:
        self._session.execute(
            update(ProfileModel)
            .where(ProfileModel.id == profile_id, ProfileModel.product == self._product)
            .values(is_platform_admin=value)
        )
        self._session.flush()

    def add(self, profile: Profile) -> None:
        if profile.product != self._product:
            raise ValueError(f"A {profile.product} profile in the {self._product} repository.")
        self._session.add(
            ProfileModel(
                id=profile.id,
                user_id=profile.user_id,
                product=profile.product.value,
                email=profile.email,
                display_name=profile.display_name,
                tenant_id=profile.tenant_id,
                role=profile.role.value,
                is_platform_admin=profile.is_platform_admin,
                created_at=datetime.now(UTC),
            )
        )
