"""do_not_contact ("BAJA") and llm_usage rows that outlive their conversation

- do_not_contact: a contact who asked not to be written to. The send job refuses every
  message to them (the one confirmation of their "BAJA" excepted) until they write again.
  Per tenant, so another business can still talk to the same number. It holds the wa_id on
  purpose and survives a contact's data deletion, so the opt-out keeps being honored.
- llm_usage.thread_id becomes nullable: deleting a contact's or a business's data keeps the
  cost rows for the totals, unlinked from the deleted conversation.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from followup_core.infrastructure.db_security import ENABLE_RLS, REVOKE_API_ROLES

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "do_not_contact",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("wa_id", sa.String(length=32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("source_message_id", sa.String(length=128), nullable=True),
        sa.Column("set_by_profile_id", sa.Uuid(), nullable=True),
        sa.Column("confirmation_message_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "source IN ('message', 'team', 'admin')", name="ck_do_not_contact_source"
        ),
    )
    op.alter_column("llm_usage", "thread_id", existing_type=sa.Uuid(), nullable=True)
    op.execute(ENABLE_RLS)
    op.execute(REVOKE_API_ROLES)


def downgrade() -> None:
    # Unlinked rows (deleted conversations) cannot point at a thread again: they go.
    op.execute("DELETE FROM llm_usage WHERE thread_id IS NULL")
    op.alter_column("llm_usage", "thread_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_table("do_not_contact")
