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
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

LEAD_STATUSES = "'qualifying', 'visit_proposed', 'human_requested', 'visit_confirmed'"


class LeadModel(Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(f"status IN ({LEAD_STATUSES})", name="ck_leads_status"),
        Index("ix_leads_tenant_last_activity", "tenant_id", "last_activity_at"),
        Index("ix_leads_tenant_created", "tenant_id", "created_at"),
        Index("ix_leads_tenant_status", "tenant_id", "status"),
        Index("ix_leads_tenant_conditions", "tenant_id", "conditions_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    # One lead per conversation thread.
    thread_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversation_threads.id"), nullable=False, unique=True
    )
    thread_key: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False)
    visitor_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    handed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hand_off_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_human_reply_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Lowercase, accent-free name, contact, contact digits and answers (Lead.search_text).
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # cumple / no_cumple / sin_datos for what the lead chose (or was shown); None = no data.
    conditions_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Where the lead came from: "web_button" (the website's WhatsApp button); None otherwise.
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)


class LeadStatusChangeModel(Base):
    __tablename__ = "lead_status_changes"
    __table_args__ = (
        CheckConstraint(f"status IN ({LEAD_STATUSES})", name="ck_lead_status_changes_status"),
        UniqueConstraint("lead_id", "position", name="uq_lead_status_changes_position"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    lead_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("leads.id"), nullable=False)
    # Order inside the lead's history (several changes can share a timestamp).
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LeadPropertyMatchModel(Base):
    """A property the agent showed to the lead (S7 inquiries, Day 6 inbox), and how the
    lead's situation compared with its conditions when the agent evaluated it."""

    __tablename__ = "lead_property_matches"
    __table_args__ = (
        Index("ix_lead_property_matches_property", "property_id"),
        CheckConstraint(
            "status IS NULL OR status IN ('cumple', 'no_cumple', 'sin_datos')",
            name="ck_lead_property_matches_status",
        ),
        CheckConstraint(
            "override_status IS NULL OR override_status IN ('cumple', 'no_cumple')",
            name="ck_lead_property_matches_override",
        ),
    )

    lead_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("leads.id"), primary_key=True)
    property_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("properties.id"), primary_key=True)
    shown_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Match.to_json(): failed requirements with their reasons, features and notes.
    match: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "Cumple igual": the team's decision (audited), over the agent's evaluation.
    override_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    overridden_by_profile_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The lead chose this property (asked to visit it), not only saw it.
    chosen: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())


class LeadConditionEventModel(Base):
    """ "No cumple" (a chosen property's requirement the lead fails), "visita evitada" (they
    said they cannot meet it before booking) and "no_fit" (nothing fits): Inicio counts
    them per month."""

    __tablename__ = "lead_condition_events"
    __table_args__ = (
        UniqueConstraint("lead_id", "dedupe", name="uq_lead_condition_events_dedupe"),
        CheckConstraint(
            "kind IN ('mismatch', 'visit_avoided', 'no_fit')", name="ck_lead_condition_events_kind"
        ),
        Index("ix_lead_condition_events_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    lead_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("leads.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    dedupe: Mapped[str] = mapped_column(String(80), nullable=False)
    property_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VisitModel(Base):
    __tablename__ = "visits"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'confirmed', 'cancelled')", name="ck_visits_status"
        ),
        Index("ix_visits_lead", "lead_id"),
        Index("ix_visits_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    lead_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("leads.id"), nullable=False)
    # Null for the sample listings shown before the agency uploads its own.
    property_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("properties.id"), nullable=True
    )
    property_label: Mapped[str] = mapped_column(String(320), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
