"""inmo24x7 property conditions: requirements and features per property, the agency's
defaults per operation, the lead's match per property shown, and their events

- `properties.conditions`: one validated JSON object (PropertyConditions). The fields are
  optional, depend on the operation and are always read together; nothing is filtered in
  SQL (the agent orders a tenant's published listings in Python), so a JSON column keeps
  the schema still as the list of conditions grows.
- `inmo_condition_settings`: "Condiciones generales" (defaults per operation and Sofía's
  switches), one row per business.
- `lead_property_matches`: the match status and reasons, stored when the agent evaluated
  them (the inbox never recomputes from a property edited later), and the team's override.
- `leads.conditions_status`: the lead's overall status, for the inbox filter.
- `lead_condition_events`: "no cumple" and "visita evitada", for Inicio's metrics.
- `property_imports.warnings`: fields ignored in a row (they do not apply to its operation).
- Data: `mortgage_approved` becomes `necesita_credito` (agent configs and lead answers; an
  approved mortgage means buying with credit, a "no" is dropped), and the agent configs
  get the two new active questions (garantia, plazo_meses).

Revision ID: inmo_0009
Revises: inmo_0008
Create Date: 2026-11-16

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from followup_core.infrastructure.db_security import ENABLE_RLS, REVOKE_API_ROLES
from sqlalchemy.dialects import postgresql

revision: str = "inmo_0009"
down_revision: str | Sequence[str] | None = "inmo_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREDIT_QUESTION = {
    "key": "necesita_credito",
    "label": "Si necesita crédito hipotecario",
    "kind": "boolean",
    "options": [],
}
NEW_QUESTIONS = [
    {
        "key": "garantia",
        "label": "Qué garantía tiene para alquilar",
        "kind": "choice",
        "options": ["propietaria", "caucion", "recibo_de_sueldo", "ninguna", "otra"],
        "enabled": True,
    },
    {
        "key": "plazo_meses",
        "label": "Por cuántos meses quiere alquilar",
        "kind": "number",
        "options": [],
        "enabled": True,
    },
]


def _upgrade_config(config: dict) -> dict:
    questions = []
    for question in config.get("qualification_questions", []):
        if question.get("key") == "mortgage_approved":
            question = {**CREDIT_QUESTION, "enabled": question.get("enabled", True)}
        questions.append(question)
    keys = {question["key"] for question in questions}
    if "necesita_credito" not in keys:
        questions.append({**CREDIT_QUESTION, "enabled": True})
    questions += [question for question in NEW_QUESTIONS if question["key"] not in keys]
    return {**config, "qualification_questions": questions}


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column(
            "conditions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "property_imports",
        sa.Column(
            "warnings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_table(
        "inmo_condition_settings",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("rent", postgresql.JSONB(), nullable=False),
        sa.Column("sale", postgresql.JSONB(), nullable=False),
        sa.Column("warn_before_visit", sa.Boolean(), nullable=False),
        sa.Column("offer_alternatives", sa.Boolean(), nullable=False),
        sa.Column("notify_mismatches", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        sa.Column("status", sa.String(length=10), nullable=True),
        sa.Column("match", postgresql.JSONB(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("override_status", sa.String(length=10), nullable=True),
        sa.Column("overridden_by_profile_id", sa.Uuid(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        # The lead chose this property (asked to visit it), not only saw it.
        sa.Column("chosen", sa.Boolean(), nullable=False, server_default=sa.false()),
    ):
        op.add_column("lead_property_matches", column)
    op.create_check_constraint(
        "ck_lead_property_matches_status",
        "lead_property_matches",
        "status IS NULL OR status IN ('cumple', 'no_cumple', 'sin_datos')",
    )
    op.create_check_constraint(
        "ck_lead_property_matches_override",
        "lead_property_matches",
        "override_status IS NULL OR override_status IN ('cumple', 'no_cumple')",
    )
    op.add_column("leads", sa.Column("conditions_status", sa.String(length=10), nullable=True))
    op.create_index("ix_leads_tenant_conditions", "leads", ["tenant_id", "conditions_status"])
    op.create_table(
        "lead_condition_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        # "<kind>:<property id>" (or "<kind>:" without one): each event once per lead.
        sa.Column("dedupe", sa.String(length=80), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("lead_id", "dedupe", name="uq_lead_condition_events_dedupe"),
        sa.CheckConstraint(
            "kind IN ('mismatch', 'visit_avoided', 'no_fit')", name="ck_lead_condition_events_kind"
        ),
    )
    op.create_index(
        "ix_lead_condition_events_tenant_created",
        "lead_condition_events",
        ["tenant_id", "created_at"],
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT v.id, v.config FROM agent_config_versions v "
            "JOIN tenants t ON t.id = v.tenant_id WHERE t.product = 'inmo24x7'"
        )
    ).all()
    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE agent_config_versions SET config = CAST(:config AS jsonb) WHERE id = :id"
            ),
            {"config": json.dumps(_upgrade_config(dict(row.config))), "id": row.id},
        )
    connection.execute(
        sa.text(
            "UPDATE leads SET answers = (answers - 'mortgage_approved') || "
            "jsonb_build_object('necesita_credito', true) "
            "WHERE answers ->> 'mortgage_approved' = 'true' AND NOT answers ? 'necesita_credito'"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE leads SET answers = answers - 'mortgage_approved' "
            "WHERE answers ? 'mortgage_approved'"
        )
    )
    op.execute(ENABLE_RLS)
    op.execute(REVOKE_API_ROLES)


def downgrade() -> None:
    op.drop_table("lead_condition_events")
    op.drop_index("ix_leads_tenant_conditions", table_name="leads")
    op.drop_column("leads", "conditions_status")
    op.drop_constraint("ck_lead_property_matches_override", "lead_property_matches")
    op.drop_constraint("ck_lead_property_matches_status", "lead_property_matches")
    for name in (
        "chosen",
        "overridden_at",
        "overridden_by_profile_id",
        "override_status",
        "evaluated_at",
        "match",
        "status",
    ):
        op.drop_column("lead_property_matches", name)
    op.drop_table("inmo_condition_settings")
    op.drop_column("property_imports", "warnings")
    op.drop_column("properties", "conditions")
