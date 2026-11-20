from datetime import datetime
from typing import Any
from uuid import UUID

from followup_core.infrastructure.db import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class PropertyModel(Base):
    __tablename__ = "properties"
    __table_args__ = (
        # A link is unique among the agency's own listings; a Tokko property with a sale and a
        # rent is two listings with the same public link, told apart by the operation.
        Index(
            "uq_properties_tenant_link",
            "tenant_id",
            "link",
            unique=True,
            postgresql_where=text("source = 'manual'"),
        ),
        Index(
            "uq_properties_external",
            "tenant_id",
            "source",
            "external_id",
            "operation",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        CheckConstraint("source IN ('manual', 'tokko')", name="ck_properties_source"),
        CheckConstraint("operation IN ('sale', 'rent')", name="ck_properties_operation"),
        CheckConstraint("currency IN ('ARS', 'USD')", name="ck_properties_currency"),
        CheckConstraint("status IN ('published', 'paused')", name="ck_properties_status"),
        CheckConstraint("price > 0", name="ck_properties_price"),
        CheckConstraint("rooms >= 1", name="ck_properties_rooms"),
        Index("ix_properties_tenant_status_operation", "tenant_id", "status", "operation"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(String(200), nullable=False)
    operation: Mapped[str] = mapped_column(String(10), nullable=False)
    zone: Mapped[str] = mapped_column(String(80), nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rooms: Mapped[int] = mapped_column(Integer, nullable=False)
    link: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    # Lowercase, accent-free address and zone, for search without the unaccent extension.
    search_text: Mapped[str] = mapped_column(String(300), nullable=False)
    # PropertyConditions.to_json(): requirements and features, only those set.
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # manual (form or spreadsheet) or tokko; a Tokko listing keeps Tokko's id and code.
    source: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'manual'"))
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PropertyImportModel(Base):
    __tablename__ = "property_imports"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    created_by_profile_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    created: Mapped[int] = mapped_column(Integer, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, nullable=False)
    columns: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    failed_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    # Cells ignored because they do not apply to the row's operation.
    warnings: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConditionSettingsModel(Base):
    """ "Condiciones generales": the agency's defaults per operation and Sofía's switches."""

    __tablename__ = "inmo_condition_settings"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    rent: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sale: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    warn_before_visit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    offer_alternatives: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notify_mismatches: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
