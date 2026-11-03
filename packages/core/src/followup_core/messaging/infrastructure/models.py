from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from followup_core.infrastructure.db import Base


class WhatsAppConnectionModel(Base):
    __tablename__ = "whatsapp_connections"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=False, unique=True
    )
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    waba_id: Mapped[str] = mapped_column(String(64), nullable=False)
    display_phone_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verified_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(String(10), nullable=False)
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    template_language: Mapped[str] = mapped_column(String(20), nullable=False)
    visit_template_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    visit_template_language: Mapped[str] = mapped_column(
        String(20), nullable=False, default="es_AR"
    )
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    business_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quality_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    business_verification: Mapped[str] = mapped_column(
        String(10), nullable=False, default="unknown"
    )
    failing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WhatsAppSignupModel(Base):
    """Embedded Signup progress per tenant, so a failed step can be retried."""

    __tablename__ = "whatsapp_signups"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    waba_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False)
    business_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    step: Mapped[str] = mapped_column(String(15), nullable=False)
    token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    pin_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WebhookCounterModel(Base):
    """Webhook requests per hour and kind (received, signature_rejected): no payloads."""

    __tablename__ = "webhook_counters"

    hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class WhatsAppInboundEventModel(Base):
    __tablename__ = "whatsapp_inbound_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    wamid: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=True)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False)
    wa_id: Mapped[str] = mapped_column(String(32), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    choice_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    # The raw notification: personal data, purged after 30 days.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WhatsAppOutboundModel(Base):
    __tablename__ = "whatsapp_outbound"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    message_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversation_messages.id"), nullable=False
    )
    part: Mapped[int] = mapped_column(Integer, nullable=False)
    wa_id: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    wamid: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # When Meta accepted it (statuses later overwrite `updated_at`).
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
