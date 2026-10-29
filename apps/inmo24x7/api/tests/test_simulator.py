from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from inmo24x7_api.container import get_language_model, get_simulator_daily_limit
from inmo24x7_api.main import app
from sqlalchemy import text
from test_setup_endpoints import Account, _body, _set_role


@pytest.fixture
def owner(client: TestClient, auth) -> Account:
    return Account(client, auth)


def _send(account: Account, message: str, path: str = "/simulator") -> dict:
    response = account.post(f"{path}/messages", {"text": message})
    assert response.status_code == 200, response.json()
    return response.json()


def _known(body: dict) -> dict[str, str | None]:
    return {row["key"]: row["value"] for row in body["known"]}


def test_get_creates_nothing_and_shows_the_empty_panel(owner: Account, db_session) -> None:
    body = owner.get("/simulator").json()

    assert body["thread"] is None
    assert body["messages"] == []
    assert body["uses_sample_properties"] is True
    assert body["config_outdated"] is False
    assert (body["agent_name"], body["business_name"]) == ("Sofía", "Inmobiliaria Sur")
    assert body["known"] == [
        {"key": "operation", "label": "Si busca comprar o alquilar", "value": None},
        {"key": "zone", "label": "Zona o barrio", "value": None},
        {"key": "budget", "label": "Presupuesto", "value": None},
        {
            "key": "mortgage_approved",
            "label": "Si tiene crédito hipotecario aprobado",
            "value": None,
        },
        {"key": "rooms", "label": "Cantidad de ambientes", "value": None},
        {"key": "visitor_name", "label": "Nombre", "value": None},
        {"key": "contact", "label": "Contacto", "value": None},
    ]
    assert db_session.scalar(text("SELECT count(*) FROM conversation_threads")) == 0


def test_chat_fills_the_panel_and_the_transcript(owner: Account) -> None:
    first = _send(owner, "Hola")
    assert first["messages"][0]["text"].startswith("¡Hola! Soy Sofía, de Inmobiliaria Sur.")
    assert first["messages"][0]["author"] == "agent"

    _send(owner, "Quiero alquilar")
    with_cards = _send(owner, "Palermo")
    cards = with_cards["messages"][0]["cards"]
    assert cards and cards[0]["price_label"].endswith("por mes")
    assert with_cards["messages"][1]["cards"] is None
    assert _known(with_cards)["operation"] == "Alquiler"
    assert _known(with_cards)["zone"] == "Palermo"

    body = owner.get("/simulator").json()
    assert body["thread"]["key"] == f"{owner.tenant_id}:simulator:{owner.user_id}.1"
    assert body["thread"]["agent_config_version"] == 0
    assert [(m["direction"], m["author"]) for m in body["messages"][:2]] == [
        ("inbound", "visitor"),
        ("outbound", "agent"),
    ]
    assert len(body["messages"]) == 7
    assert body["known"] == with_cards["known"]


def test_reset_starts_a_new_thread(owner: Account) -> None:
    _send(owner, "Hola")
    before = owner.get("/simulator").json()["thread"]["key"]

    reset = owner.post("/simulator/reset", {})

    assert reset.status_code == 200
    body = reset.json()
    assert body["thread"]["key"] != before
    assert body["thread"]["key"].endswith(f"{owner.user_id}.2")
    assert body["messages"] == []
    assert all(row["value"] is None for row in body["known"])
    greeting = _send(owner, "Hola de nuevo")["messages"][0]["text"]
    assert greeting.startswith("¡Hola! Soy Sofía")
    assert owner.get("/simulator").json()["thread"]["key"] == body["thread"]["key"]


def test_tenants_never_see_each_others_threads(client: TestClient, auth) -> None:
    a = Account(client, auth, "Agencia A")
    b = Account(client, auth, "Agencia B")
    _send(a, "Hola")

    assert b.get("/simulator").json()["messages"] == []
    assert b.get("/simulator").json()["business_name"] == "Agencia B"
    _send(b, "Hola")
    assert len(a.get("/simulator").json()["messages"]) == 2


def test_any_role_can_use_the_simulator(owner: Account, db_session) -> None:
    _set_role(db_session, owner.user_id, "viewer")

    assert owner.post("/simulator/messages", {"text": "Hola"}).status_code == 200


@pytest.mark.parametrize("message", ["", "   ", "x" * 1001])
def test_messages_must_have_1_to_1000_characters(owner: Account, message: str) -> None:
    response = owner.post("/simulator/messages", {"text": message})

    assert response.status_code == 422
    assert response.json() == {"code": "validation_error"}


def test_llm_failure_returns_503_and_stores_nothing(owner: Account, db_session) -> None:
    _send(owner, "Hola")
    app.dependency_overrides[get_language_model] = lambda: FakeLanguageModel(TimeoutError())
    try:
        response = owner.post("/simulator/messages", {"text": "Quiero alquilar"})
    finally:
        app.dependency_overrides[get_language_model] = lambda: FakeLanguageModel()

    assert response.status_code == 503
    assert response.json() == {"code": "agent_unavailable"}
    body = owner.get("/simulator").json()
    assert len(body["messages"]) == 2
    assert _known(body)["operation"] is None
    assert db_session.scalar(text("SELECT count(*) FROM conversation_messages")) == 2


def test_failure_on_the_first_message_creates_no_thread(owner: Account, db_session) -> None:
    app.dependency_overrides[get_language_model] = lambda: FakeLanguageModel(TimeoutError())
    try:
        assert owner.post("/simulator/messages", {"text": "Hola"}).status_code == 503
    finally:
        app.dependency_overrides[get_language_model] = lambda: FakeLanguageModel()

    assert db_session.scalar(text("SELECT count(*) FROM conversation_threads")) == 0
    assert db_session.scalar(text("SELECT count(*) FROM checkpoints")) == 0


def test_daily_limit_returns_429(owner: Account) -> None:
    app.dependency_overrides[get_simulator_daily_limit] = lambda: 2
    try:
        _send(owner, "Hola")
        owner.post("/simulator/reset", {})
        _send(owner, "Hola otra vez")  # the limit counts every thread of the tenant
        response = owner.post("/simulator/messages", {"text": "una más"})
    finally:
        app.dependency_overrides.pop(get_simulator_daily_limit)

    assert response.status_code == 429
    assert response.json() == {"code": "simulator_limit_reached"}


def test_agent_tested_flips_after_the_first_message(owner: Account) -> None:
    def facts() -> dict:
        return owner.get("/onboarding").json()["checklist"]["facts"]

    assert facts()["agent_tested"] is False
    owner.post("/simulator/reset", {})
    assert facts()["agent_tested"] is False

    _send(owner, "Hola")

    assert facts()["agent_tested"] is True


def test_config_changes_mark_the_thread_outdated_until_reset(owner: Account) -> None:
    _send(owner, "Hola")
    setup = owner.get("/agent-setup").json()
    owner.put("/agent-setup", _body(setup, config={**setup["config"], "agent_name": "Lucía"}))

    outdated = owner.get("/simulator").json()
    assert outdated["config_outdated"] is True
    assert outdated["agent_name"] == "Sofía"  # the thread keeps the version it started with

    reset = owner.post("/simulator/reset", {}).json()
    assert reset["config_outdated"] is False
    assert reset["thread"]["agent_config_version"] == 1
    assert _send(owner, "Hola")["messages"][0]["text"].startswith("¡Hola! Soy Lucía")


# --- Admin ("Probar su agente") ---------------------------------------------------------


def test_admin_endpoints_require_the_admin_flag(owner: Account) -> None:
    path = f"/admin/tenants/{owner.tenant_id}/simulator"

    assert owner.get(path).json() == {"code": "admin_required"}
    assert owner.post(f"{path}/messages", {"text": "Hola"}).json() == {"code": "admin_required"}
    assert owner.post(f"{path}/reset", {}).json() == {"code": "admin_required"}


def test_admin_tests_a_tenant_agent_in_their_own_thread(
    client: TestClient, auth, owner: Account
) -> None:
    admin = Account(client, auth, "Plataforma")
    auth.make_admin(admin.user_id)
    path = f"/admin/tenants/{owner.tenant_id}/simulator"

    first = _send(admin, "Hola", path)

    assert first["messages"][0]["text"].startswith("¡Hola! Soy Sofía, de Inmobiliaria Sur.")
    body = admin.get(path).json()
    assert body["thread"]["key"] == f"{owner.tenant_id}:simulator:{admin.user_id}.1"
    assert body["business_name"] == "Inmobiliaria Sur"
    # The owner's own simulator and checklist are untouched.
    assert owner.get("/simulator").json()["messages"] == []
    assert owner.get("/onboarding").json()["checklist"]["facts"]["agent_tested"] is False

    reset = admin.post(f"{path}/reset", {}).json()
    assert reset["thread"]["key"].endswith(f"{admin.user_id}.2")


def test_admin_gets_404_for_unknown_tenants(client: TestClient, auth) -> None:
    admin = Account(client, auth, "Plataforma")
    auth.make_admin(admin.user_id)
    path = f"/admin/tenants/{uuid4()}/simulator"

    for response in (
        admin.get(path),
        admin.post(f"{path}/messages", {"text": "Hola"}),
        admin.post(f"{path}/reset", {}),
    ):
        assert response.status_code == 404
        assert response.json() == {"code": "tenant_not_found"}
