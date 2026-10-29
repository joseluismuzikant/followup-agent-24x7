"""conversation threads and messages (the transcript source of truth)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("visitor_id", sa.String(length=120), nullable=False),
        sa.Column("agent_config_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_by_profile_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_conversation_threads_key"),
        sa.CheckConstraint(
            "channel IN ('simulator', 'whatsapp')", name="ck_conversation_threads_channel"
        ),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_conversation_threads_status"),
        sa.CheckConstraint(
            "agent_config_version >= 0", name="ck_conversation_threads_config_version"
        ),
    )
    op.create_index(
        "ix_conversation_threads_started_by",
        "conversation_threads",
        ["tenant_id", "channel", "started_by_profile_id", "created_at"],
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("author", sa.String(length=10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["conversation_threads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound')", name="ck_conversation_messages_direction"
        ),
        sa.CheckConstraint(
            "author IN ('visitor', 'agent', 'human', 'system')",
            name="ck_conversation_messages_author",
        ),
    )
    op.create_index(
        "ix_conversation_messages_thread_seq", "conversation_messages", ["thread_id", "seq"]
    )
    op.create_index(
        "ix_conversation_messages_direction_created",
        "conversation_messages",
        ["direction", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("conversation_messages")
    op.drop_table("conversation_threads")
