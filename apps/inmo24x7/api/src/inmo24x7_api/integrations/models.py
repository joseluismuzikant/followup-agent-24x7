from datetime import datetime
from typing import Any
from uuid import UUID

from followup_core.infrastructure.db import Base
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

PROVIDERS = "'tokko', 'webhook', 'widget'"


class IntegrationModel(Base):
    """One row per agency and integration. `credentials` is TokenCipher ciphertext."""

    __tablename__ = "inmo_integrations"
    __table_args__ = (
        CheckConstraint(f"provider IN ({PROVIDERS})", name="ck_integrations_provider"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_id: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_delivery_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SyncReportModel(Base):
    """Each sync's outcome, like a spreadsheet import report (failed: [{external_id, title,
    reason}])."""

    __tablename__ = "inmo_sync_reports"
    __table_args__ = (Index("ix_sync_reports_tenant_started", "tenant_id", "started_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created: Mapped[int] = mapped_column(Integer, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, nullable=False)
    paused: Mapped[int] = mapped_column(Integer, nullable=False)
    unchanged: Mapped[int] = mapped_column(Integer, nullable=False)
    failed: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)


class LeadDeliveryModel(Base):
    """One delivery of a lead (or a test) to Tokko or the webhook: status only, never the
    payload, so deleting a contact leaves nothing of it here once its lead goes."""

    __tablename__ = "inmo_lead_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'retrying', 'delivered', 'failed')",
            name="ck_lead_deliveries_status",
        ),
        Index("ix_lead_deliveries_tenant_provider", "tenant_id", "provider", "created_at"),
        Index("ix_lead_deliveries_lead", "lead_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    lead_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("leads.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
