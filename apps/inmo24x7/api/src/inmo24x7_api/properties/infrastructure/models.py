from datetime import datetime
from typing import Any
from uuid import UUID

from followup_core.infrastructure.db import Base
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class PropertyModel(Base):
    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("tenant_id", "link", name="uq_properties_tenant_link"),
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
