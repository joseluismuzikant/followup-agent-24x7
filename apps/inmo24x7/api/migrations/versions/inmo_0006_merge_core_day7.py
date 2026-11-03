"""merge the inmo24x7 chain with core 0010 (day 7)

Core revisions chain to the core head, so core 0010 left a second head next to inmo_0005.
This merge keeps `alembic upgrade head` single-headed (see ARCHITECTURE.md, "Migrations").

Revision ID: inmo_0006
Revises: inmo_0005, 0010
Create Date: 2026-11-05

"""

from collections.abc import Sequence

revision: str = "inmo_0006"
down_revision: str | Sequence[str] | None = ("inmo_0005", "0010")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
