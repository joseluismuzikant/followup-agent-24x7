from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from followup_core.infrastructure.db import Base


class ThreadModel(Base):
    __tablename__ = "conversation_threads"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    visitor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_by_profile_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MessageModel(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    thread_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversation_threads.id"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    author: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    trace_run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
