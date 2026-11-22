"""llm_usage.operation 'read_listing': a listing page read into a property draft

inmo24x7's "Cargar desde un link" asks the model for what the page's structured data did not
say. Its calls are rows like any other (channel "panel", no thread), billed by tokens.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-21

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_llm_usage_operation", "llm_usage", type_="check")
    op.create_check_constraint(
        "ck_llm_usage_operation",
        "llm_usage",
        "operation IN ('extract', 'compose_reply', 'transcribe', 'read_listing')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM llm_usage WHERE operation = 'read_listing'")
    op.drop_constraint("ck_llm_usage_operation", "llm_usage", type_="check")
    op.create_check_constraint(
        "ck_llm_usage_operation",
        "llm_usage",
        "operation IN ('extract', 'compose_reply', 'transcribe')",
    )
