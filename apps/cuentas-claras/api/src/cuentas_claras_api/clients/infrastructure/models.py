from datetime import datetime
from uuid import UUID

from followup_core.infrastructure.db import Base
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class ClientModel(Base):
    __tablename__ = "cc_clients"
    __table_args__ = (UniqueConstraint("tenant_id", "cuit", name="uq_cc_clients_tenant_cuit"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # name folded for matching ("edificio guemes sa"): imports find clients by it.
    name_key: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cuit: Mapped[str | None] = mapped_column(String(11), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    no_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
