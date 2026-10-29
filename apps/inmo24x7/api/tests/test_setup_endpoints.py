from typing import Annotated
from uuid import UUID, uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from followup_core.tenancy.application.agent_setup import SaveAgentSetup
from followup_core.tenancy.infrastructure.setup_repositories import (
    SqlAlchemyAgentConfigRepository,
    SqlAlchemyBusinessSettingsRepository,
)
from inmo24x7_api.container import get_setup_defaults, save_agent_setup_use_case
from inmo24x7_api.database import get_session
from inmo24x7_api.main import app
from sqlalchemy import text
from sqlalchemy.orm import Session


class Account:
    def __init__(self, client: TestClient, auth, name: str = "Inmobiliaria Sur") -> None:
        self.client = client
        self.user_id = uuid4()
        self.email = f"{self.user_id}@example.com"
        token = auth.register(self.user_id, email=self.email)
        self.headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/me/sign-up",
            json={"business_name": name, "business_type": "inmobiliaria"},
            headers=self.headers,
        )
        assert response.status_code == 201
        self.tenant_id = UUID(response.json()["tenant"]["id"])

    def get(self, path: str):
        return self.client.get(path, headers=self.headers)

    def put(self, path: str, body: dict):
        return self.client.put(path, json=body, headers=self.headers)

    def post(self, path: str, body: dict):
        return self.client.post(path, json=body, headers=self.headers)


@pytest.fixture
def owner(client: TestClient, auth) -> Account:
    return Account(client, auth)


def _body(setup: dict, **overrides) -> dict:
    body = {
        "config": setup["config"],
        "business_hours": setup["business_hours"],
        "notification_emails": setup["notification_emails"],
    }
    body.update(overrides)
    return body


def _set_role(db_session, user_id: UUID, role: str) -> None:
    db_session.execute(
        text("UPDATE profiles SET role = :role WHERE id = :id"), {"role": role, "id": user_id}
    )
    db_session.commit()


# --- Sign-up creates the setup records ---------------------------------------------


def test_sign_up_creates_onboarding_and_default_settings(owner: Account) -> None:
    onboarding = owner.get("/onboarding").json()
    setup = owner.get("/agent-setup").json()

    assert onboarding["current_step"] == "agent"
    assert [step["step"] for step in onboarding["completed_steps"]] == ["business"]
    assert onboarding["finished"] is False
    assert setup["version"] == 0
    assert setup["updated_at"] is None
    assert setup["config"]["agent_name"] == "Sofía"
    assert setup["config"]["tone"] == "warm"
    assert [question["key"] for question in setup["config"]["qualification_questions"]] == [
        "operation",
        "zone",
        "budget",
        "mortgage_approved",
        "rooms",
    ]
    assert setup["config"] == setup["defaults"]
    assert setup["notification_emails"] == [owner.email]
    assert len(setup["business_hours"]) == 5


# --- Onboarding ---------------------------------------------------------------------


def test_onboarding_advances_in_order_and_resumes(owner: Account) -> None:
    assert owner.post("/onboarding/advance", {"to_step": "whatsapp"}).json() == {
        "code": "onboarding_step_invalid"
    }
    assert owner.post("/onboarding/advance", {"to_step": "nonsense"}).status_code == 422

    advanced = owner.post("/onboarding/advance", {"to_step": "try"})
    assert advanced.status_code == 200
    assert advanced.json()["current_step"] == "try"

    # Going back is a no-op that never uncompletes anything.
    back = owner.post("/onboarding/advance", {"to_step": "agent"}).json()
    assert back["current_step"] == "try"
    assert [step["step"] for step in back["completed_steps"]] == ["business", "agent"]

    assert owner.get("/onboarding").json()["current_step"] == "try"


def test_onboarding_finishes_at_done(owner: Account) -> None:
    for step in ("try", "whatsapp", "done"):
        response = owner.post("/onboarding/advance", {"to_step": step})
        assert response.status_code == 200

    body = owner.get("/onboarding").json()
    assert body["finished"] is True
    assert body["current_step"] == "done"


def test_checklist_reflects_the_saved_agent(owner: Account) -> None:
    before = owner.get("/onboarding").json()["checklist"]
    assert (before["ready_count"], before["total"]) == (1, 5)
    assert [item["key"] for item in before["items"]] == [
        "account",
        "agent",
        "whatsapp",
        "properties",
        "meta",
    ]

    setup = owner.get("/agent-setup").json()
    owner.put("/agent-setup", _body(setup))

    after = owner.get("/onboarding").json()["checklist"]
    assert after["ready_count"] == 2
    assert after["facts"]["agent_configured"] is True
    assert after["facts"]["agent_tested"] is False


# --- Agent setup ----------------------------------------------------------------------


def test_saving_creates_a_version_only_when_something_changed(owner: Account) -> None:
    setup = owner.get("/agent-setup").json()

    first = owner.put("/agent-setup", _body(setup)).json()
    same = owner.put("/agent-setup", _body(first)).json()
    changed_config = {**first["config"], "agent_name": "Lucía", "tone": "formal"}
    changed = owner.put("/agent-setup", _body(first, config=changed_config)).json()

    assert (first["version"], same["version"], changed["version"]) == (1, 1, 2)
    assert changed["config"]["agent_name"] == "Lucía"
    versions = owner.get("/agent-setup/versions").json()
    assert [item["version"] for item in versions] == [2, 1]
    assert versions[0]["author_email"] == owner.email


def test_saving_hours_and_emails_is_atomic_with_the_config(owner: Account) -> None:
    setup = owner.get("/agent-setup").json()
    renamed = {**setup["config"], "agent_name": "Lucía"}

    rejected = owner.put(
        "/agent-setup",
        _body(setup, config=renamed, notification_emails=["not-an-email"]),
    )

    assert rejected.status_code == 422
    assert rejected.json() == {"code": "notification_email_invalid"}
    after = owner.get("/agent-setup").json()
    assert after["version"] == 0
    assert after["config"]["agent_name"] == "Sofía"

    saved = owner.put(
        "/agent-setup",
        _body(
            setup,
            config=renamed,
            business_hours=[{"weekday": 5, "opens": "09:00", "closes": "13:00"}],
            notification_emails=["Uno@x.com", "dos@x.com"],
        ),
    ).json()
    assert saved["notification_emails"] == ["uno@x.com", "dos@x.com"]
    assert saved["business_hours"] == [{"weekday": 5, "opens": "09:00", "closes": "13:00"}]
    assert owner.get("/tenant/settings").json()["notification_emails"] == [
        "uno@x.com",
        "dos@x.com",
    ]


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda b: b["config"].update(agent_name="  "), "agent_name_invalid"),
        (lambda b: b["config"].update(agent_name="x" * 41), "agent_name_invalid"),
        (lambda b: b["config"].update(qualification_questions=[]) or b, None),
        (
            lambda b: b["config"]["qualification_questions"].append(
                dict(b["config"]["qualification_questions"][0])
            ),
            "questions_invalid",
        ),
        (
            lambda b: b["config"]["qualification_questions"][0].update(label=""),
            "questions_invalid",
        ),
        (lambda b: b.update(notification_emails=[]), "notification_email_invalid"),
        (
            lambda b: b.update(
                business_hours=[{"weekday": 0, "opens": "18:00", "closes": "09:00"}]
            ),
            "team_hours_invalid",
        ),
        (
            lambda b: b.update(business_hours=[{"weekday": 0, "opens": "late", "closes": "09:00"}]),
            "team_hours_invalid",
        ),
    ],
)
def test_validation_codes(owner: Account, mutate, code) -> None:
    body = _body(owner.get("/agent-setup").json())
    mutate(body)

    response = owner.put("/agent-setup", body)

    if code is None:  # An empty question list is valid.
        assert response.status_code == 200
    else:
        assert response.status_code == 422
        assert response.json() == {"code": code}


def test_invalid_tone_is_a_validation_error(owner: Account) -> None:
    body = _body(owner.get("/agent-setup").json())
    body["config"]["tone"] = "grumpy"

    response = owner.put("/agent-setup", body)

    assert response.status_code == 422
    assert response.json() == {"code": "validation_error"}


def _with_questions(setup: dict, *questions: dict) -> dict:
    config = {**setup["config"], "qualification_questions": list(questions)}
    return _body(setup, config=config)


def _new_question(label: str) -> dict:
    return {"label": label, "kind": "text"}


def _keys(setup: dict) -> list[str]:
    return [question["key"] for question in setup["config"]["qualification_questions"]]


def test_server_assigns_custom_keys_and_never_reuses_them(owner: Account) -> None:
    setup = owner.get("/agent-setup").json()
    zone = setup["config"]["qualification_questions"][1]

    added = owner.put(
        "/agent-setup",
        _with_questions(setup, zone, _new_question("Mascotas"), _new_question("Cochera")),
    ).json()
    assert _keys(added) == ["zone", "custom_1", "custom_2"]

    pets = added["config"]["qualification_questions"][1]
    owner.put("/agent-setup", _with_questions(added, zone, pets))  # deletes custom_2
    readded = owner.put(
        "/agent-setup", _with_questions(added, zone, pets, _new_question("Balcón"))
    ).json()

    assert _keys(readded) == ["zone", "custom_1", "custom_3"]


@pytest.mark.parametrize("key", ["custom_1", "made_up"])
def test_unknown_question_keys_are_rejected(owner: Account, key: str) -> None:
    setup = owner.get("/agent-setup").json()

    response = owner.put(
        "/agent-setup", _with_questions(setup, {"key": key, "label": "Algo", "kind": "text"})
    )

    assert response.status_code == 422
    assert response.json() == {"code": "questions_invalid"}
    assert owner.get("/agent-setup").json()["version"] == 0


class _StaleAgentConfigRepository(SqlAlchemyAgentConfigRepository):
    """Reads the latest version as it was before another request saved."""

    def latest(self, tenant_id):
        return None


def test_concurrent_saves_conflict_instead_of_failing(owner: Account) -> None:
    setup = owner.get("/agent-setup").json()
    assert owner.put("/agent-setup", _body(setup)).json()["version"] == 1

    def stale_save(session: Annotated[Session, Depends(get_session)]) -> SaveAgentSetup:
        return SaveAgentSetup(
            _StaleAgentConfigRepository(session),
            SqlAlchemyBusinessSettingsRepository(session),
            get_setup_defaults(),
        )

    app.dependency_overrides[save_agent_setup_use_case] = stale_save
    try:
        renamed = {**setup["config"], "agent_name": "Lucía"}
        response = owner.put("/agent-setup", _body(setup, config=renamed))
    finally:
        app.dependency_overrides.pop(save_agent_setup_use_case)

    assert response.status_code == 409
    assert response.json() == {"code": "agent_setup_conflict"}
    after = owner.get("/agent-setup").json()
    assert (after["version"], after["config"]["agent_name"]) == (1, "Sofía")


def test_version_history_is_capped_at_20(owner: Account) -> None:
    setup = owner.get("/agent-setup").json()
    for index in range(22):
        owner.put(
            "/agent-setup",
            _body(setup, config={**setup["config"], "agent_name": f"Agente {index}"}),
        )

    versions = owner.get("/agent-setup/versions").json()

    assert len(versions) == 20
    assert versions[0]["version"] == 22


# --- Tenant settings --------------------------------------------------------------------


def test_tenant_settings_round_trip_and_rename_keeps_the_slug(
    client: TestClient, owner: Account
) -> None:
    current = owner.get("/tenant/settings").json()
    assert current["business_name"] == "Inmobiliaria Sur"
    assert current["timezone"] == "America/Argentina/Buenos_Aires"

    updated = owner.put(
        "/tenant/settings",
        {
            "business_name": "Sur Propiedades",
            "business_type": "desarrolladora",
            "business_hours": [],
            "notification_emails": ["ventas@x.com"],
        },
    )

    assert updated.status_code == 200
    assert updated.json()["business_name"] == "Sur Propiedades"
    me = owner.get("/me").json()
    assert me["tenant"]["name"] == "Sur Propiedades"
    assert me["tenant"]["slug"] == "inmobiliaria-sur"
    assert owner.get("/agent-setup").json()["business_hours"] == []


def test_tenant_settings_validation(owner: Account) -> None:
    base = {
        "business_name": "Sur",
        "business_type": "inmobiliaria",
        "business_hours": [],
        "notification_emails": ["a@x.com"],
    }

    assert owner.put("/tenant/settings", {**base, "business_name": " "}).json() == {
        "code": "tenant_name_invalid"
    }
    assert owner.put("/tenant/settings", {**base, "business_type": "x"}).json() == {
        "code": "business_type_invalid"
    }
    assert owner.put("/tenant/settings", {**base, "notification_emails": []}).json() == {
        "code": "notification_email_invalid"
    }


# --- Roles ---------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["manager"])
def test_managers_can_write(client: TestClient, owner: Account, db_session, role: str) -> None:
    _set_role(db_session, owner.user_id, role)
    setup = owner.get("/agent-setup").json()

    assert owner.put("/agent-setup", _body(setup)).status_code == 200
    assert owner.post("/onboarding/advance", {"to_step": "try"}).status_code == 200


@pytest.mark.parametrize("role", ["agent", "viewer"])
def test_agents_and_viewers_read_but_cannot_write(
    client: TestClient, owner: Account, db_session, role: str
) -> None:
    setup = owner.get("/agent-setup").json()
    _set_role(db_session, owner.user_id, role)

    assert owner.get("/agent-setup").status_code == 200
    assert owner.get("/agent-setup/versions").status_code == 200
    assert owner.get("/tenant/settings").status_code == 200
    assert owner.get("/onboarding").status_code == 200

    forbidden = {"code": "forbidden"}
    assert owner.put("/agent-setup", _body(setup)).json() == forbidden
    assert owner.post("/onboarding/advance", {"to_step": "try"}).json() == forbidden
    assert (
        owner.put(
            "/tenant/settings",
            {
                "business_name": "X",
                "business_type": "inmobiliaria",
                "business_hours": [],
                "notification_emails": ["a@x.com"],
            },
        ).json()
        == forbidden
    )


# --- Scoping ----------------------------------------------------------------------------------


def test_tenants_never_see_or_change_each_other(client: TestClient, auth) -> None:
    a = Account(client, auth, "Agencia A")
    b = Account(client, auth, "Agencia B")
    setup_a = a.get("/agent-setup").json()
    a.put(
        "/agent-setup",
        _body(setup_a, config={**setup_a["config"], "agent_name": "Solo de A"}),
    )
    a.post("/onboarding/advance", {"to_step": "try"})
    a.put(
        "/tenant/settings",
        {
            "business_name": "Agencia A SA",
            "business_type": "corredor",
            "business_hours": [],
            "notification_emails": ["a@a.com"],
        },
    )

    assert b.get("/agent-setup").json()["config"]["agent_name"] == "Sofía"
    assert b.get("/agent-setup").json()["version"] == 0
    assert b.get("/agent-setup/versions").json() == []
    assert b.get("/onboarding").json()["current_step"] == "agent"
    assert b.get("/tenant/settings").json()["business_name"] == "Agencia B"
    assert b.get("/tenant/settings").json()["notification_emails"] == [b.email]

    # A tenant id in the request is ignored: the body has no such field and the path
    # has no parameter, so B's writes only ever touch B's tenant.
    setup_b = b.get("/agent-setup").json()
    forged = _body(setup_b, tenant_id=str(a.tenant_id))
    b.put("/agent-setup", forged)
    assert a.get("/agent-setup").json()["config"]["agent_name"] == "Solo de A"
    assert a.get("/agent-setup").json()["version"] == 1


def test_endpoints_require_a_profile(client: TestClient, auth) -> None:
    token = auth.register(uuid4(), email="nobody@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    for path in ("/onboarding", "/agent-setup", "/agent-setup/versions", "/tenant/settings"):
        response = client.get(path, headers=headers)
        assert response.status_code == 404, path
        assert response.json() == {"code": "profile_not_found"}

    assert client.get("/onboarding").status_code == 401
