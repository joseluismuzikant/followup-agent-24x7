"""inmo24x7 inbox: last team reply, a normalized search column, and indexes for the inbox
tabs and the dashboard

Revision ID: inmo_0005
Revises: inmo_0004
Create Date: 2026-11-04

"""

import re
import unicodedata
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "inmo_0005"
down_revision: str | Sequence[str] | None = "inmo_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def _search_text(name: str | None, contact: str | None, answers: dict[str, Any]) -> str:
    # A frozen copy of Lead.search_text at the time of this revision.
    words = [name or "", contact or "", re.sub(r"\D", "", contact or "")]
    words += [str(value) for value in answers.values() if isinstance(value, str | int)]
    return _normalize(" ".join(word for word in words if word))[:2000]


def upgrade() -> None:
    op.add_column("leads", sa.Column("last_human_reply_at", sa.DateTime(timezone=True)))
    op.add_column("leads", sa.Column("search_text", sa.Text(), nullable=False, server_default=""))
    op.create_index("ix_leads_tenant_created", "leads", ["tenant_id", "created_at"])
    op.create_index("ix_leads_tenant_status", "leads", ["tenant_id", "status"])
    op.create_index("ix_visits_created", "visits", ["created_at"])

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, visitor_name, contact, answers FROM leads")).all()
    for row in rows:
        bind.execute(
            sa.text("UPDATE leads SET search_text = :text WHERE id = :id"),
            {"id": row.id, "text": _search_text(row.visitor_name, row.contact, row.answers)},
        )


def downgrade() -> None:
    op.drop_index("ix_visits_created", table_name="visits")
    op.drop_index("ix_leads_tenant_status", table_name="leads")
    op.drop_index("ix_leads_tenant_created", table_name="leads")
    op.drop_column("leads", "search_text")
    op.drop_column("leads", "last_human_reply_at")
