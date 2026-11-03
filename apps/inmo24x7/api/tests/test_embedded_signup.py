"""Embedded Signup (S4) and connection health end to end: the panel posts what Meta's popup
returned, the API runs the steps against the Graph API (mocked at the HTTP level), and an
auth error from Meta stops sending until the business reconnects."""

import pytest
from fastapi.testclient import TestClient
from followup_core.messaging.application.health import health_sweep_job
from followup_core.scheduling.infrastructure.queue import SqlAlchemyJobQueue
from inmo24x7_api.container import get_messaging_services
from inmo24x7_api.main import app
from test_setup_endpoints import Account, _body, _set_role
from whatsapp_fakes import (
    PHONE_NUMBER_ID,
    FakeGraph,
    WhatsAppWorld,
    build_services,
    connect,
    make_sessions,
    simulate_whatsapp,
)

SIGNUP = {
    "code": "AQB-code-from-meta",
    "waba_id": "waba-es-1",
    "phone_number_id": PHONE_NUMBER_ID,
    "business_id": "biz-1",
}


class World(WhatsAppWorld):
    owner: Account
    admin: Account


@pytest.fixture
def world(client: TestClient, auth, database):
    graph = FakeGraph()
    services = build_services(graph)
    app.dependency_overrides[get_messaging_services] = lambda: services
    world = World(client, make_sessions(database), services, graph)
    world.owner = Account(client, auth)
    setup = world.owner.get("/agent-setup").json()
    always = [{"weekday": day, "opens": "00:00", "closes": "23:30"} for day in range(7)]
    world.owner.put("/agent-setup", _body(setup, business_hours=always))
    world.admin = Account(client, auth, "Plataforma")
    auth.make_admin(world.admin.user_id)
    yield world
    app.dependency_overrides.pop(get_messaging_services, None)


def signup(world: World, **changes):
    return world.owner.post("/whatsapp/embedded-signup", {**SIGNUP, **changes})


def audit(world: World, action: str) -> list[dict]:
    return [
        row.details
        for row in world.sql(
            "SELECT details FROM audit_events WHERE tenant_id = :t AND action = :a ORDER BY at",
            t=world.owner.tenant_id,
            a=action,
        )
    ]


# --- Embedded Signup ---------------------------------------------------------------------------


def test_signup_runs_every_step_and_connects_the_number(world: World) -> None:
    response = signup(world)

    assert response.status_code == 200, response.json()
    body = response.json()
    assert (body["status"], body["display_phone_number"]) == ("connected", "+54 9 11 5555-0100")
    assert (body["business_verification"], body["quality_rating"]) == ("verified", "GREEN")
    assert body["error"] is None and body["signup_step"] is None
    assert "EAAB" not in response.text and "access_token" not in response.text
    steps = [(method, path.rsplit("/", 1)[-1]) for method, path, _ in world.graph.requests]
    assert steps[:3] == [("GET", "access_token"), ("POST", "subscribed_apps"), ("POST", "register")]
    register = next(body for _, path, body in world.graph.requests if path.endswith("/register"))
    assert register["messaging_product"] == "whatsapp"
    assert len(register["pin"]) == 6 and register["pin"].isdigit()
    # The token is stored encrypted, never in clear.
    (stored,) = world.sql("SELECT access_token_encrypted FROM whatsapp_connections")
    assert stored[0].startswith("k1:") and "EAAB" not in stored[0]
    assert audit(world, "whatsapp_connected")[0]["source"] == "embedded_signup"
    facts = world.owner.get("/onboarding").json()["checklist"]["facts"]
    assert facts["whatsapp_connected"] and facts["meta_business_verified"]


@pytest.mark.parametrize(
    ("suffix", "step", "code"),
    [
        ("/subscribed_apps", "subscribed", "token_revoked"),
        ("/register", "registered", "pin_mismatch"),
    ],
)
def test_a_failed_step_is_resumed_without_meta_popup(
    world: World, suffix: str, step: str, code: str
) -> None:
    meta_code = 190 if suffix == "/subscribed_apps" else 133005
    world.graph.fail_on[suffix] = [(400, meta_code)]

    failed = signup(world)

    assert failed.status_code == 502
    assert (failed.json()["code"], failed.json()["step"]) == ("whatsapp_signup_failed", step)
    assert failed.json()["error"]["code"] == code
    status = world.owner.get("/whatsapp").json()
    assert status["status"] == "not_connected"
    assert status["signup_step"] is not None and status["signup_error"]["code"] == code
    assert audit(world, "whatsapp_signup_failed") == [{"step": step, "meta_code": str(meta_code)}]

    retried = world.owner.post("/whatsapp/embedded-signup/retry", {})

    assert retried.status_code == 200, retried.json()
    assert retried.json()["status"] == "connected"
    # The 30-second code was exchanged once; the steps before the failure did not repeat.
    assert world.calls("/oauth/access_token") == 1
    assert world.calls("/subscribed_apps") == (2 if suffix == "/subscribed_apps" else 1)
    pins = [b["pin"] for _, p, b in world.graph.requests if p.endswith("/register")]
    assert len(set(pins)) == 1  # the same PIN on every attempt


def test_a_failed_code_exchange_needs_the_popup_again(world: World) -> None:
    world.graph.fail_on["/oauth/access_token"] = [(400, 100)]

    failed = signup(world)
    retried = world.owner.post("/whatsapp/embedded-signup/retry", {})

    assert (failed.status_code, failed.json()["step"]) == (502, "exchanged")
    assert (retried.status_code, retried.json()) == (409, {"code": "whatsapp_signup_restart"})
    assert signup(world, code="a-new-code").json()["status"] == "connected"


def test_signup_is_idempotent_and_a_number_belongs_to_one_business(
    world: World, client: TestClient, auth
) -> None:
    assert signup(world).status_code == 200
    calls = len(world.graph.requests)

    again = world.owner.post("/whatsapp/embedded-signup/retry", {})
    other = Account(client, auth, "Otra inmobiliaria")
    taken = other.post("/whatsapp/embedded-signup", SIGNUP)

    assert again.json()["status"] == "connected"
    assert len(world.graph.requests) == calls  # nothing asked to Meta again
    assert (taken.status_code, taken.json()) == (409, {"code": "whatsapp_phone_number_taken"})


def test_only_owners_and_managers_connect(world: World, db_session) -> None:
    _set_role(db_session, world.owner.user_id, "agent")

    assert signup(world).status_code == 403
    assert world.owner.post("/whatsapp/embedded-signup/retry", {}).status_code == 403


def test_a_cancelled_or_failed_popup_is_recorded_without_personal_data(world: World) -> None:
    response = world.owner.post(
        "/whatsapp/embedded-signup/abandoned",
        {"event": "CANCEL", "current_step": "PHONE_NUMBER_SETUP"},
    )
    error = world.owner.post(
        "/whatsapp/embedded-signup/abandoned", {"event": "ERROR", "error_code": "2388012"}
    )

    assert (response.status_code, response.json()) == (200, {"error": None})
    assert error.json()["error"]["title"] == "Ese número ya está en otra cuenta"
    assert audit(world, "whatsapp_signup_abandoned") == [
        {"event": "CANCEL", "step": "PHONE_NUMBER_SETUP", "meta_code": None},
        {"event": "ERROR", "step": None, "meta_code": "2388012"},
    ]


def test_admins_retry_the_signup_and_send_a_reconnect_link(world: World) -> None:
    world.graph.fail_on["/register"] = [(400, 133016)]
    signup(world)
    path = f"/admin/tenants/{world.owner.tenant_id}/whatsapp"

    retried = world.client.post(f"{path}/retry-signup", headers=world.admin.headers)
    link = world.client.post(f"{path}/reconnect-link", headers=world.admin.headers)
    world.run()

    assert retried.status_code == 200 and retried.json()["status"] == "connected"
    assert (link.status_code, link.json()) == (202, {"recipients": 1})
    (email,) = world.emails.sent
    assert email.to == [world.owner.email]
    assert "https://panel.example.com/configuracion#whatsapp" in email.text
    assert audit(world, "reconnect_link_sent") == [{"recipients": 1}]


# --- Health -------------------------------------------------------------------------------------


def _connected(world: World) -> None:
    response = connect(world.client, world.admin.headers, world.owner.tenant_id)
    assert response.status_code == 200


def test_a_revoked_token_stops_sending_until_the_business_reconnects(world: World) -> None:
    _connected(world)
    world.graph.fail_next = [(401, 190)]

    world.chat("Hola")
    world.chat("Quiero alquilar")

    # One failed attempt, no retry loop: everything else waits for the connection.
    assert world.graph.accepted == 0
    assert len(world.graph.sent()) == 1
    assert {status for status, _, _ in world.outbound()} == {"waiting_connection"}
    assert all(job[0] == "done" for job in world.jobs("whatsapp.send"))
    status = world.owner.get("/whatsapp").json()
    assert status["status"] == "error" and status["failing_since"] is not None
    assert status["error"]["title"] == "El permiso de Meta venció"
    assert audit(world, "whatsapp_error") == [{"meta_code": "190"}]

    _connected(world)  # the manual fallback; Embedded Signup resumes the same way
    world.run()

    # Sent in order (Meta accepted each one; delivery statuses come by webhook later).
    assert all(wamid for _, wamid, _ in world.outbound())
    replies = [b["text"]["body"] for b in world.graph.sent()[1:] if b.get("type") == "text"]
    assert replies and replies == [b["text"]["body"] for b in world.graph.sent()[1:]]
    assert world.owner.get("/whatsapp").json()["error"] is None


def test_the_health_check_reads_quality_and_recovers_a_revoked_token(world: World) -> None:
    _connected(world)
    world.graph.fail_on[f"/{PHONE_NUMBER_ID}"] = [(401, 190)]
    with world.sessions() as session:
        SqlAlchemyJobQueue(session).enqueue(health_sweep_job(world.clock()))
        session.commit()

    world.run()

    assert world.jobs("whatsapp.health_check") == [("done", 1)]
    assert world.owner.get("/whatsapp").json()["status"] == "error"

    world.graph.quality_rating = "YELLOW"
    world.execute("UPDATE jobs SET dedupe_key = NULL")  # the next 6-hour slot
    with world.sessions() as session:
        SqlAlchemyJobQueue(session).enqueue(health_sweep_job(world.clock()))
        session.commit()
    world.run()

    status = world.owner.get("/whatsapp").json()
    assert (status["status"], status["quality_rating"]) == ("connected", "YELLOW")


def test_account_update_webhooks_move_the_connection(world: World) -> None:
    _connected(world)

    def update(event: str, **value) -> None:
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "waba-test-1",
                    "changes": [{"field": "account_update", "value": {"event": event, **value}}],
                }
            ],
        }
        assert world.post(payload) == 200

    update(
        "PARTNER_CLIENT_CERTIFICATION_STATUS_UPDATE",
        partner_client_certification_info={"status": "APPROVED"},
    )
    assert world.owner.get("/whatsapp").json()["business_verification"] == "verified"

    update("DISABLED_UPDATE", ban_info={"waba_ban_state": "DISABLE"})
    disabled = world.owner.get("/whatsapp").json()
    assert (disabled["status"], disabled["error"]["code"]) == ("error", "account_disabled")

    update("DISABLED_UPDATE", ban_info={"waba_ban_state": "REINSTATE"})
    assert world.owner.get("/whatsapp").json()["status"] == "connected"

    update("PARTNER_APP_UNINSTALLED", waba_info={"waba_id": "waba-test-1"})
    removed = world.owner.get("/whatsapp").json()
    assert (removed["status"], removed["error"]["code"]) == ("error", "app_removed")
    events = [d["event"] for d in audit(world, "whatsapp_account_update")]
    assert events == [
        "PARTNER_CLIENT_CERTIFICATION_STATUS_UPDATE",
        "DISABLED_UPDATE",
        "DISABLED_UPDATE",
        "PARTNER_APP_UNINSTALLED",
    ]


def test_webhook_requests_are_counted_by_hour(world: World) -> None:
    _connected(world)
    world.say("Hola")
    payload = simulate_whatsapp.message_payload("x", phone_number_id=PHONE_NUMBER_ID)

    assert world.post(payload, secret="wrong-secret") == 401

    counts = dict(world.sql("SELECT kind, count FROM webhook_counters"))
    assert counts == {"received": 1, "signature_rejected": 1}
