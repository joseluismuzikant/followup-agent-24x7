from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from followup_core.infrastructure.db import Base


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    trial_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OnboardingModel(Base):
    __tablename__ = "tenant_onboarding"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    current_step: Mapped[str] = mapped_column(String(20), nullable=False)
    completed_steps: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BusinessSettingsModel(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    business_type: Mapped[str] = mapped_column(String(30), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    team_hours: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    notification_emails: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentConfigVersionModel(Base):
    __tablename__ = "agent_config_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "version", name="uq_agent_config_version"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_profile_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("profiles.id"), nullable=False
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
