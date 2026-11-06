from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from followup_core.infrastructure.db import Base
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class InvoiceModel(Base):
    __tablename__ = "cc_invoices"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "invoice_type", "point_of_sale", "number", name="uq_cc_invoices_number"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("cc_clients.id"), nullable=False)
    invoice_type: Mapped[str] = mapped_column(String(1), nullable=False)
    point_of_sale: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid_via: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvoiceImportModel(Base):
    """One import's report; the failed rows (personal data) only feed the error download."""

    __tablename__ = "cc_invoice_imports"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    created_by_profile_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    created: Mapped[int] = mapped_column(Integer, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False)
    columns: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    failed_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
