from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from followup_core.tenancy.domain.product import Product

from ..domain.account import Account
from ..domain.invitation import Invitation, hash_token
from .models import AccountModel, InvitationModel


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _maybe(value: datetime | None) -> datetime | None:
    return _aware(value) if value is not None else None


def _account(model: AccountModel) -> Account:
    return Account(
        user_id=model.user_id,
        email=model.email,
        must_change_password=model.must_change_password,
        created_at=_aware(model.created_at),
        password_changed_at=_maybe(model.password_changed_at),
    )


class SqlAlchemyAccountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: UUID) -> Account | None:
        model = self._session.get(AccountModel, user_id)
        return _account(model) if model is not None else None

    def get_by_email(self, email: str) -> Account | None:
        model = self._session.scalar(
            select(AccountModel).where(AccountModel.email == email.strip().lower())
        )
        return _account(model) if model is not None else None

    def add(self, account: Account) -> None:
        self._session.add(
            AccountModel(
                user_id=account.user_id,
                email=account.email.strip().lower(),
                must_change_password=account.must_change_password,
                created_at=account.created_at,
                password_changed_at=account.password_changed_at,
            )
        )
        self._session.flush()

    def set_must_change(self, user_id: UUID, value: bool, at: datetime | None = None) -> None:
        values: dict[str, object] = {"must_change_password": value}
        if at is not None:
            values["password_changed_at"] = at
        self._session.execute(
            update(AccountModel).where(AccountModel.user_id == user_id).values(**values)
        )
        self._session.flush()


def _invitation(model: InvitationModel) -> Invitation:
    return Invitation(
        id=model.id,
        product=Product(model.product),
        email=model.email,
        tenant_id=model.tenant_id,
        token_hash=model.token_hash,
        created_at=_aware(model.created_at),
        expires_at=_aware(model.expires_at),
        accepted_at=_maybe(model.accepted_at),
        revoked_at=_maybe(model.revoked_at),
    )


class SqlAlchemyInvitationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, invitation_id: UUID) -> Invitation | None:
        model = self._session.get(InvitationModel, invitation_id)
        return _invitation(model) if model is not None else None

    def get_by_token(self, token: str) -> Invitation | None:
        model = self._session.scalar(
            select(InvitationModel).where(InvitationModel.token_hash == hash_token(token))
        )
        return _invitation(model) if model is not None else None

    def latest_for(self, product: Product, email: str) -> Invitation | None:
        model = self._session.scalar(
            select(InvitationModel)
            .where(
                InvitationModel.product == product.value,
                InvitationModel.email == email.strip().lower(),
            )
            .order_by(InvitationModel.created_at.desc())
            .limit(1)
        )
        return _invitation(model) if model is not None else None

    def add(self, invitation: Invitation) -> None:
        self._session.execute(
            update(InvitationModel)
            .where(
                InvitationModel.product == invitation.product.value,
                InvitationModel.email == invitation.email,
                InvitationModel.accepted_at.is_(None),
                InvitationModel.revoked_at.is_(None),
            )
            .values(revoked_at=invitation.created_at)
        )
        self._session.add(
            InvitationModel(
                id=invitation.id,
                product=invitation.product.value,
                email=invitation.email,
                tenant_id=invitation.tenant_id,
                token_hash=invitation.token_hash,
                created_at=invitation.created_at,
                expires_at=invitation.expires_at,
            )
        )
        self._session.flush()

    def mark_accepted(self, invitation_id: UUID, at: datetime) -> None:
        self._session.execute(
            update(InvitationModel)
            .where(InvitationModel.id == invitation_id)
            .values(accepted_at=at)
        )
        self._session.flush()
