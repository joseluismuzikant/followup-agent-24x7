from datetime import datetime
from uuid import UUID

from followup_core.infrastructure.db import Base
from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class PaymentRequestModel(Base):
    __tablename__ = "cc_payment_requests"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("cc_clients.id"), nullable=False)
    # SHA-256 of the link's token (the token itself is only in the link).
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    invoice_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentSettingsModel(Base):
    """ "Datos para transferencia" (Day 9B adds the Mercado Pago account next to it)."""

    __tablename__ = "cc_payment_settings"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    cbu_or_alias: Mapped[str] = mapped_column(String(22), nullable=False)
    holder: Mapped[str] = mapped_column(String(120), nullable=False)
    bank: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
