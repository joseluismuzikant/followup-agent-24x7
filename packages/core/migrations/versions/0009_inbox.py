"""inbox: thread control (takeover), who wrote a team message, sent time of WhatsApp parts,
and the visit confirmation template per connection

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_threads",
        sa.Column("control", sa.String(length=10), nullable=False, server_default="agent"),
    )
    op.add_column(
        "conversation_threads", sa.Column("controlled_by_profile_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "conversation_threads",
        sa.Column("control_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_conversation_threads_control", "conversation_threads", "control IN ('agent', 'human')"
    )
    op.add_column("conversation_messages", sa.Column("author_profile_id", sa.Uuid(), nullable=True))
    op.add_column(
        "whatsapp_outbound", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "whatsapp_connections",
        sa.Column("visit_template_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "whatsapp_connections",
        sa.Column(
            "visit_template_language",
            sa.String(length=20),
            nullable=False,
            server_default="es_AR",
        ),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_connections", "visit_template_language")
    op.drop_column("whatsapp_connections", "visit_template_name")
    op.drop_column("whatsapp_outbound", "sent_at")
    op.drop_column("conversation_messages", "author_profile_id")
    op.drop_constraint("ck_conversation_threads_control", "conversation_threads", type_="check")
    op.drop_column("conversation_threads", "control_changed_at")
    op.drop_column("conversation_threads", "controlled_by_profile_id")
    op.drop_column("conversation_threads", "control")
