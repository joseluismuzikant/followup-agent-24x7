from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from followup_core.infrastructure.db import Base
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class ReminderPolicyModel(Base):
    __tablename__ = "cc_reminder_policies"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    # [{"id", "offset_days", "kind", "template_kind", "active"}], in order.
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    window_preset: Mapped[str] = mapped_column(String(20), nullable=False)
    window_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    window_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    skip_holidays: Mapped[bool] = mapped_column(Boolean, nullable=False)
    pause_on_promise: Mapped[bool] = mapped_column(Boolean, nullable=False)
    configured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WhatsAppTemplateModel(Base):
    __tablename__ = "cc_whatsapp_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "kind", "version", name="uq_cc_templates_version"),
        Index("ix_cc_templates_meta_id", "meta_template_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Meta's raw value (APPROVED, PENDING, REJECTED, PAUSED, ...) or ours before Meta has it.
    status: Mapped[str] = mapped_column(Text, nullable=False)
    meta_template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReminderSendModel(Base):
    __tablename__ = "cc_reminder_sends"
    __table_args__ = (
        UniqueConstraint("client_id", "day", name="uq_cc_reminder_sends_client_day"),
        Index("ix_cc_reminder_sends_tenant_day", "tenant_id", "day"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("cc_clients.id"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    template_name: Mapped[str] = mapped_column(Text, nullable=False)
    invoice_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    # [[invoice_id, step_id, offset_days]]
    steps: Mapped[list[list[Any]]] = mapped_column(JSONB, nullable=False)
    message_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("conversation_messages.id"), nullable=True
    )
    payment_request_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cc_payment_requests.id"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReminderEventModel(Base):
    __tablename__ = "cc_reminder_events"
    __table_args__ = (
        Index("ix_cc_reminder_events_invoice", "tenant_id", "invoice_id"),
        Index("ix_cc_reminder_events_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("cc_clients.id"), nullable=False)
    invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cc_invoices.id"), nullable=True
    )
    step_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    offset_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(60), nullable=True)
    send_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cc_reminder_sends.id"), nullable=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
