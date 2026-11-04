"""merge the inmo24x7 chain with core 0011, and lock every table of both chains

Core revisions chain to the core head, so core 0011 left a second head next to inmo_0006.
This merge keeps `alembic upgrade head` single-headed (see ARCHITECTURE.md, "Migrations").
It also runs 0011's SQL again: on a fresh database the product tables are created after
0011 (the chains are separate branches), and this merge is the first point after both.

Revision ID: inmo_0007
Revises: inmo_0006, 0011
Create Date: 2026-11-06

"""

from collections.abc import Sequence

from alembic import op
from followup_core.infrastructure.db_security import ENABLE_RLS, REVOKE_API_ROLES

revision: str = "inmo_0007"
down_revision: str | Sequence[str] | None = ("inmo_0006", "0011")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(ENABLE_RLS)
    op.execute(REVOKE_API_ROLES)


def downgrade() -> None:
    pass
