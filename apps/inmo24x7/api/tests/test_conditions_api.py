"""Property conditions through the API and the database: "Condiciones generales", a
property's own conditions over the agency's, and a conversation that does not meet them
(the inbox block and filter, "Cumple igual", Inicio's counts and the hand-off email)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from followup_core.notifications.infrastructure.smtp import RecordingEmailSender
from followup_core.scheduling.domain.jobs import Job, JobStatus
from followup_core.tenancy.infrastructure.setup_repositories import (
    SqlAlchemyBusinessSettingsRepository,
)
from inmo24x7_api.container import get_lead_use_case
from inmo24x7_api.leads.application.notify import HANDOFF_EMAIL_JOB, SendLeadEmail
from sqlalchemy import text
from test_setup_endpoints import Account, _body, _set_role

GORRITI = {
    "title": "2 ambientes luminoso",
    "address": "Gorriti 4800",
    "operation": "rent",
    "zone": "Palermo",
    "price": 850000,
    "rooms": 2,
    "link": "https://x.test/gorriti",
    "conditions": {"garantias": ["caucion"], "contrato_minimo_meses": 24},
}


@pytest.fixture
def owner(client: TestClient, auth) -> Account:
    account = Account(client, auth)
    setup = account.get("/agent-setup").json()
    always = [{"weekday": day, "opens": "00:00", "closes": "23:30"} for day in range(7)]
    assert account.put("/agent-setup", _body(setup, business_hours=always)).status_code == 200
    return account


def _say(account: Account, message: str) -> dict:
    response = account.post("/simulator/messages", {"text": message})
    assert response.status_code == 200, response.json()
    return response.json()


def _settings(**overrides) -> dict:
    return {
        "rent": {},
        "sale": {},
        "warn_before_visit": True,
        "offer_alternatives": True,
        "notify_mismatches": True,
        **overrides,
    }


def test_condition_settings_default_and_save(owner: Account, db_session) -> None:
    assert owner.get("/condition-settings").json() == {
        "rent": {key: None for key in _keys()},
        "sale": {key: None for key in _keys()},
        "warn_before_visit": True,
        "offer_alternatives": True,
        "notify_mismatches": True,
    }

    saved = owner.put(
        "/condition-settings",
        _settings(
            rent={
                "garantias": ["caucion", "propietaria"],
                "contrato_minimo_meses": 24,
                "apto_credito": True,
            },
            sale={"apto_credito": True},
            notify_mismatches=False,
        ),
    ).json()

    assert saved["rent"]["garantias"] == ["caucion", "propietaria"]
    # A sale field never applies to a rent.
    assert saved["rent"]["apto_credito"] is None
    assert saved["sale"]["apto_credito"] is True
    assert saved["notify_mismatches"] is False
    actions = db_session.execute(text("SELECT action FROM audit_events")).scalars().all()
    assert "condition_settings_saved" in actions


def test_agents_cannot_change_the_conditions(owner: Account, db_session) -> None:
    _set_role(db_session, owner.user_id, "agent")

    assert owner.put("/condition-settings", _settings()).status_code == 403


def test_a_property_shows_which_conditions_come_from_the_default(owner: Account) -> None:
    owner.put("/condition-settings", _settings(rent={"garantias": ["caucion"], "mascotas": False}))

    created = owner.post(
        "/properties",
        {**GORRITI, "conditions": {"mascotas": True, "condiciones": "Requiere dos garantías"}},
    ).json()

    assert created["conditions"]["mascotas"] is True
    assert created["effective_conditions"]["garantias"] == ["caucion"]
    assert created["effective_conditions"]["mascotas"] is True
    assert created["from_defaults"] == ["garantias"]
    invalid = owner.post(
        "/properties",
        {**GORRITI, "link": "https://x.test/b", "conditions": {"contrato_minimo_meses": 200}},
    )
    assert invalid.status_code == 422


def _mismatch_conversation(owner: Account) -> str:
    assert owner.post("/properties", GORRITI).status_code == 201
    for message in ["Hola", "Quiero alquilar por 1 mes", "Palermo"]:
        _say(owner, message)
    asked = _say(owner, "Me interesa la de Gorriti")
    assert "garantía" in asked["messages"][-1]["text"]
    check = _say(owner, "No tengo garantía")
    assert check["messages"][-1]["text"].endswith("¿Podrías cumplir con eso?")
    _say(owner, "no puedo")
    (lead,) = owner.get("/leads?include_test=true").json()["items"]
    return lead["id"]


def test_a_lead_that_does_not_meet_the_requirements(owner: Account, db_session) -> None:
    lead_id = _mismatch_conversation(owner)

    listed = owner.get("/leads?include_test=true&conditions=no_cumple").json()["items"]
    assert [item["id"] for item in listed] == [lead_id]
    assert listed[0]["conditions_status"] == "no_cumple"
    assert owner.get("/leads?include_test=true&conditions=cumple").json()["items"] == []

    conditions = owner.get(f"/leads/{lead_id}").json()["conditions"]
    assert conditions["status"] == "no_cumple"
    assert {fact["key"]: fact["value"] for fact in conditions["facts"]} == {
        "garantia": "No tiene garantía",
        "plazo_meses": "1 mes",
    }
    (shown,) = conditions["properties"]
    assert shown["chosen"] is True and shown["status"] == "no_cumple"
    assert shown["reasons"] == [
        "pide seguro de caución; no tiene garantía",
        "pide contrato de 2 años; busca 1 mes",
    ]

    # Inicio counts real leads only.
    db_session.execute(text("UPDATE leads SET is_test = false"))
    db_session.commit()
    kpis = owner.get("/dashboard").json()["conditions"]
    assert (kpis["mismatches"], kpis["visits_avoided"]) == (1, 1)


def test_the_team_can_mark_cumple_igual(owner: Account, db_session) -> None:
    lead_id = _mismatch_conversation(owner)
    property_id = owner.get(f"/leads/{lead_id}").json()["conditions"]["properties"][0][
        "property_id"
    ]

    detail = owner.post(
        f"/leads/{lead_id}/properties/{property_id}/conditions", {"status": "cumple"}
    ).json()

    assert detail["conditions"]["status"] == "cumple"
    (shown,) = detail["conditions"]["properties"]
    assert (shown["status"], shown["agent_status"], shown["overridden"]) == (
        "cumple",
        "no_cumple",
        True,
    )
    assert shown["summary"] == "Cumple igual (lo marcó el equipo)"
    audit = db_session.execute(
        text("SELECT details FROM audit_events WHERE action = 'condition_match_overridden'")
    ).scalar_one()
    assert audit["status"] == "cumple" and audit["property_id"] == property_id
    back = owner.post(
        f"/leads/{lead_id}/properties/{property_id}/conditions", {"status": None}
    ).json()
    assert back["conditions"]["status"] == "no_cumple"
    missing = owner.post(f"/leads/{lead_id}/properties/{uuid4()}/conditions", {"status": "cumple"})
    assert missing.json() == {"code": "property_not_shown"}


@pytest.mark.parametrize("notify", [True, False])
def test_the_hand_off_email_follows_the_switch(owner: Account, db_session, notify: bool) -> None:
    lead_id = _mismatch_conversation(owner)
    db_session.execute(text("UPDATE leads SET is_test = false"))
    db_session.commit()
    sender = RecordingEmailSender()
    handler = SendLeadEmail(
        get_lead_use_case(db_session),
        SqlAlchemyBusinessSettingsRepository(db_session),
        sender,
        "https://panel.test",
        notify_mismatches=lambda _tenant_id: notify,
    )

    handler(
        Job(
            uuid4(),
            HANDOFF_EMAIL_JOB,
            {"tenant_id": str(owner.tenant_id), "lead_id": lead_id},
            datetime.now(UTC),
            JobStatus.RUNNING,
            1,
            1,
        )
    )

    if notify:
        (email,) = sender.sent
        assert "Condiciones: Gorriti 4800: No cumple: pide seguro de caución" in email.text
    else:
        assert sender.sent == []


def _keys() -> list[str]:
    return [
        "garantias",
        "contrato_minimo_meses",
        "temporal",
        "amueblado",
        "mascotas",
        "apto_profesional",
        "apto_credito",
        "acepta_financiacion",
        "acepta_permuta",
        "condiciones",
    ]
