"""root LangSmith run id on outbound messages

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversation_messages", sa.Column("trace_run_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversation_messages", "trace_run_id")
