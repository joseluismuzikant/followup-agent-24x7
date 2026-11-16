"""inmo_0009 on data written before it: `mortgage_approved` becomes `necesita_credito`
(agent configs and lead answers) and the configs get the two new active questions."""

import json

from alembic import command
from alembic.config import Config
from conftest import ROOT, TEST_DATABASE_URL
from sqlalchemy import text
from test_setup_endpoints import Account

OLD_QUESTIONS = [
    {
        "key": "operation",
        "label": "Si busca comprar o alquilar",
        "kind": "choice",
        "options": ["compra", "alquiler"],
        "enabled": True,
    },
    {"key": "zone", "label": "Zona o barrio", "kind": "text", "options": [], "enabled": True},
    {
        "key": "mortgage_approved",
        "label": "Si tiene crédito hipotecario aprobado",
        "kind": "boolean",
        "options": [],
        "enabled": False,
    },
    {
        "key": "rooms",
        "label": "Cantidad de ambientes",
        "kind": "number",
        "options": [],
        "enabled": True,
    },
]


def test_the_old_mortgage_question_and_answers_become_necesita_credito(
    client, auth, db_session
) -> None:
    owner = Account(client, auth)
    setup = owner.get("/agent-setup").json()
    owner.put(
        "/agent-setup",
        {
            "config": setup["config"],
            "business_hours": setup["business_hours"],
            "notification_emails": setup["notification_emails"],
        },
    )
    assert owner.post("/simulator/messages", {"text": "Hola"}).status_code == 200
    old_config = {**setup["config"], "qualification_questions": OLD_QUESTIONS}
    db_session.execute(
        text("UPDATE agent_config_versions SET config = CAST(:config AS jsonb)"),
        {"config": json.dumps(old_config)},
    )
    db_session.execute(
        text(
            "UPDATE leads SET answers = "
            '\'{"operation": "compra", "mortgage_approved": true}\'::jsonb'
        )
    )
    db_session.commit()
    db_session.close()

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    command.downgrade(config, "inmo_0008")
    command.upgrade(config, "heads")

    questions = db_session.execute(
        text("SELECT config -> 'qualification_questions' FROM agent_config_versions")
    ).scalar_one()
    assert [q["key"] for q in questions] == [
        "operation",
        "zone",
        "necesita_credito",
        "rooms",
        "garantia",
        "plazo_meses",
    ]
    credit = questions[2]
    assert credit["label"] == "Si necesita crédito hipotecario"
    assert credit["enabled"] is False  # the owner had turned it off: it stays off
    answers = db_session.execute(text("SELECT answers FROM leads")).scalar_one()
    assert answers == {"operation": "compra", "necesita_credito": True}
    # The agent reads the migrated config.
    assert owner.get("/agent-setup").status_code == 200
