"""merge the inmo24x7 chain with core 0008 (scheduling and messaging)

Core revisions chain to the core head, never to a product revision, so core 0007/0008 left a
second head next to inmo_0002. This merge keeps `alembic upgrade head` single-headed.

Revision ID: inmo_0003
Revises: inmo_0002, 0008
Create Date: 2026-11-03

"""

from collections.abc import Sequence

revision: str = "inmo_0003"
down_revision: str | Sequence[str] | None = ("inmo_0002", "0008")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
