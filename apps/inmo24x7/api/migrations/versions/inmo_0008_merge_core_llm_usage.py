"""merge the inmo24x7 chain with core 0012 (llm_usage)

Keeps `alembic upgrade head` single-headed (see ARCHITECTURE.md, "Migrations"), and runs
the RLS SQL again for any table created on either branch since inmo_0007.

Revision ID: inmo_0008
Revises: inmo_0007, 0012
Create Date: 2026-11-07

"""

from collections.abc import Sequence

from alembic import op
from followup_core.infrastructure.db_security import ENABLE_RLS, REVOKE_API_ROLES

revision: str = "inmo_0008"
down_revision: str | Sequence[str] | None = ("inmo_0007", "0012")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(ENABLE_RLS)
    op.execute(REVOKE_API_ROLES)


def downgrade() -> None:
    pass
