from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from followup_core.infrastructure.db import Base


class ProfileModel(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "product", name="uq_profiles_user_product"),
        UniqueConstraint("email", "product", name="uq_profiles_email_product"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # The Supabase user: one per person, one profile per product.
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    product: Mapped[str] = mapped_column(String(20), nullable=False, server_default="inmo24x7")
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountModel(Base):
    """One per person (per Supabase user), shared by the products."""

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("email", name="uq_accounts_email"),)

    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class InvitationModel(Base):
    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_invitations_token_hash"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    product: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DevPasswordModel(Base):
    """AUTH_MODE=dev only: the local stand-in for Supabase Auth's passwords."""

    __tablename__ = "dev_passwords"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
