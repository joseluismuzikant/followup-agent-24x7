"""whatsapp_connections: room for Meta's raw name_status and quality_rating

Meta's display-name review answers AVAILABLE_WITHOUT_REVIEW (24 characters), which did not
fit varchar(20). Production got the same ALTERs by hand first; changing a column to the type
it already has is a no-op in Postgres, so this upgrade succeeds there too.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WIDENED = {"name_status": 64, "quality_rating": 32}


def upgrade() -> None:
    for column, length in _WIDENED.items():
        op.alter_column(
            "whatsapp_connections",
            column,
            type_=sa.String(length=length),
            existing_type=sa.String(length=20),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Longer values are cut to fit (a downgrade must not fail on AVAILABLE_WITHOUT_REVIEW).
    for column, length in _WIDENED.items():
        op.alter_column(
            "whatsapp_connections",
            column,
            type_=sa.String(length=20),
            existing_type=sa.String(length=length),
            existing_nullable=True,
            postgresql_using=f"left({column}, 20)",
        )
