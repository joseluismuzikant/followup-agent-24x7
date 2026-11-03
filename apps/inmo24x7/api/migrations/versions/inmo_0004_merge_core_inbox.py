"""merge the inmo24x7 chain with core 0009 (inbox)

Core revisions chain to the core head, so core 0009 left a second head next to inmo_0003.
This merge keeps `alembic upgrade head` single-headed (see ARCHITECTURE.md, "Migrations").

Revision ID: inmo_0004
Revises: inmo_0003, 0009
Create Date: 2026-11-04

"""

from collections.abc import Sequence

revision: str = "inmo_0004"
down_revision: str | Sequence[str] | None = ("inmo_0003", "0009")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
