"""WhatsApp end to end against the test database: webhook → event → job → agent turn →
outbound parts → send job, plus emails and the admin connection endpoints. The Graph API is
mocked at the HTTP level; nothing reaches Meta or a model."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from followup_core.conversation.domain.errors import LlmUnavailableError
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from inmo24x7_api.container import get_messaging_services
from inmo24x7_api.main import app
from test_setup_endpoints import Account, _body, _set_role
from whatsapp_fakes import (
    APP_SECRET,
    PHONE_NUMBER_ID,
    VERIFY_TOKEN,
    VISITOR,
    FakeGraph,
    WhatsAppWorld,
    build_services,
    connect,
    make_sessions,
    simulate_whatsapp,
)


class World(WhatsAppWorld):
    owner: Account
    admin: Account


def _world(client: TestClient, auth, database, llm=None, sender: str = "cloud") -> World:
    graph = FakeGraph()
    services = build_services(graph)
    app.dependency_overrides[get_messaging_services] = lambda: services
    world = World(client, make_sessions(database), services, graph, llm)
    world.owner = Account(client, auth)
    setup = world.owner.get("/agent-setup").json()
    always = [{"weekday": day, "opens": "00:00", "closes": "23:30"} for day in range(7)]
    world.owner.put("/agent-setup", _body(setup, business_hours=always))
    world.admin = Account(client, auth, "Plataforma")
    auth.make_admin(world.admin.user_id)
    response = connect(client, world.admin.headers, world.owner.tenant_id, sender=sender)
    assert response.status_code == 200, response.json()
    return world


@pytest.fixture
def world(client: TestClient, auth, database):
    yield _world(client, auth, database)
    app.dependency_overrides.pop(get_messaging_services, None)


class FailingModel(FakeLanguageModel):
    def __init__(self) -> None:
        super().__init__(fail_with=RuntimeError("no model in the webhook"))


# --- Webhook ------------------------------------------------------------------------------


def test_verification_returns_the_challenge_only_with_the_right_token(world: World) -> None:
    ok = world.client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "42"},
    )
    assert (ok.status_code, ok.text, ok.headers["content-type"].split(";")[0]) == (
        200,
        "42",
        "text/plain",
    )
    for params in (
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"},
        {"hub.mode": "unsubscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "42"},
    ):
        assert world.client.get("/webhooks/whatsapp", params=params).status_code == 403


def test_the_signature_is_checked_over_the_raw_body(world: World) -> None:
    payload = simulate_whatsapp.message_payload("Hola", phone_number_id=PHONE_NUMBER_ID)
    compact = simulate_whatsapp.encode(payload)
    pretty = simulate_whatsapp.json.dumps(payload, indent=2).encode()

    def post(body: bytes, headers: dict[str, str]) -> int:
        return world.client.post("/webhooks/whatsapp", content=body, headers=headers).status_code

    good = simulate_whatsapp.sign(compact, APP_SECRET)
    assert post(pretty, {"X-Hub-Signature-256": good}) == 401  # same JSON, other bytes
    assert post(compact, {"X-Hub-Signature-256": simulate_whatsapp.sign(compact, "other")}) == 401
    assert post(compact, {}) == 401
    assert world.sql("SELECT count(*) FROM whatsapp_inbound_events")[0][0] == 0
    assert post(compact, {"X-Hub-Signature-256": good}) == 200


def test_the_webhook_never_calls_the_model_or_meta(client: TestClient, auth, database) -> None:
    world = _world(client, auth, database, llm=FailingModel())
    before = len(world.graph.requests)

    assert world.say("Hola, busco un 2 ambientes en Palermo") == 200

    assert len(world.graph.requests) == before
    assert world.jobs("whatsapp.process") == [("queued", 0)]
    app.dependency_overrides.pop(get_messaging_services, None)


def test_a_duplicate_wamid_is_processed_once(world: World) -> None:
    payload = simulate_whatsapp.message_payload(
        "Hola", phone_number_id=PHONE_NUMBER_ID, wamid="wamid.dup.1"
    )
    assert world.post(payload) == 200
    assert world.post(payload) == 200
    world.run()

    assert world.sql("SELECT count(*) FROM whatsapp_inbound_events")[0][0] == 1
    assert len(world.jobs("whatsapp.process")) == 1
    assert [row for row in world.transcript() if row[0] == "inbound"] == [
        ("inbound", "visitor", "Hola")
    ]


def test_an_unknown_number_is_stored_as_ignored(world: World) -> None:
    payload = simulate_whatsapp.message_payload("Hola", phone_number_id="someone-else")

    assert world.post(payload) == 200
    assert world.sql("SELECT status, tenant_id FROM whatsapp_inbound_events") == [("ignored", None)]
    assert world.jobs("whatsapp.process") == []


# --- Processing ----------------------------------------------------------------------------


def test_a_burst_gets_one_answer_with_the_messages_in_order(client, auth, database) -> None:
    llm = FakeLanguageModel()
    world = _world(client, auth, database, llm=llm)
    for message in ["hola", "busco depto para alquilar", "en Palermo"]:
        world.say(message)

    # Still inside the debounce: nothing runs yet.
    world.clock.now = world.clock.now + timedelta(seconds=1)
    world.runner.run_due()
    assert world.transcript() == []

    world.run()
    rows = world.transcript()
    assert [row[2] for row in rows if row[0] == "inbound"] == [
        "hola",
        "busco depto para alquilar",
        "en Palermo",
    ]
    # One turn: greeting, cards and the next question, after the three messages.
    first_outbound = next(i for i, row in enumerate(rows) if row[0] == "outbound")
    assert first_outbound == 3
    assert sorted(status for status, _ in world.jobs("whatsapp.process")) == ["done"] * 3
    app.dependency_overrides.pop(get_messaging_services, None)


def test_each_conversation_has_its_own_thread(world: World) -> None:
    world.say("Hola", sender=VISITOR)
    world.say("Hola", sender="5493515550000")
    world.run()

    threads = world.sql("SELECT visitor_id FROM conversation_threads ORDER BY visitor_id")
    assert [row[0] for row in threads] == ["5491155550188", "5493515550000"]


def test_whatsapp_leads_are_real_and_never_asked_for_a_phone(world: World) -> None:
    world.chat("Hola", "Quiero alquilar", "Palermo", "Me interesa la primera")
    offer = world.graph.sent()[-1]
    assert offer["type"] == "interactive"
    slot = offer["interactive"]["action"]["buttons"][0]["reply"]

    # A tap on a reply button is the same slot selection as the simulator's buttons.
    assert world.say(slot["title"], slot=slot["id"]) == 200
    world.run()
    world.chat("Me llamo Ana Pérez")

    (lead,) = world.owner.get("/leads").json()["items"]
    assert (lead["is_test"], lead["channel"], lead["contact"], lead["visitor_name"]) == (
        False,
        "whatsapp",
        "+54 9 11 5555-0188",
        "Ana Pérez",
    )
    assert lead["status"] == "visit_proposed" and lead["hand_off_reason"] == "visit"
    texts = [body.get("text", {}).get("body", "") for body in world.graph.sent()]
    assert not any("teléfono o email" in text for text in texts)
    # The hand-off event stays in the transcript and is never sent.
    assert ("outbound", "system", "El agente derivó la consulta a tu equipo") in world.transcript()
    assert not any("derivó" in text for text in texts)


def test_media_gets_a_fixed_reply_without_the_model(client, auth, database) -> None:
    world = _world(client, auth, database, llm=FailingModel())

    world.say(None, audio=True)
    world.run()

    assert world.transcript() == [
        ("inbound", "visitor", ""),
        ("outbound", "agent", "Por ahora solo puedo leer mensajes de texto. ¿Me lo escribís?"),
    ]
    assert world.sql("SELECT content_type FROM conversation_messages ORDER BY seq")[0][0] == "audio"
    assert world.graph.sent()[-1]["text"]["body"].startswith("Por ahora solo puedo leer")
    app.dependency_overrides.pop(get_messaging_services, None)


def test_processed_messages_are_marked_read(world: World) -> None:
    world.chat("Hola")

    reads = [body for _, _, body in world.graph.requests if body.get("status") == "read"]
    assert len(reads) == 1 and reads[0]["message_id"].startswith("wamid.sim.")


def test_a_model_failure_keeps_the_messages_pending_for_a_retry(client, auth, database) -> None:
    llm = FakeLanguageModel(fail_with=LlmUnavailableError("down"))
    world = _world(client, auth, database, llm=llm)
    world.say("Hola")
    world.run()

    assert world.sql("SELECT status FROM whatsapp_inbound_events") == [("pending",)]
    llm.fail_with = None
    world.run(after_seconds=60)
    assert world.sql("SELECT status FROM whatsapp_inbound_events") == [("processed",)]
    app.dependency_overrides.pop(get_messaging_services, None)


# --- Sending -------------------------------------------------------------------------------


def test_cards_are_one_text_each_with_the_link_and_slots_are_buttons(world: World) -> None:
    world.chat("Hola", "Quiero alquilar", "Palermo")
    sent = world.graph.sent()
    cards = [body for body in sent if body["text"]["body"].startswith("*")]
    assert cards and all(body["text"]["preview_url"] for body in cards)
    title, _address, price, *rest = cards[0]["text"]["body"].split("\n")
    assert title.startswith("*") and title.endswith("*") and "$" in price
    # Sample listings link to the panel's absolute /ejemplo page.
    assert rest[-1].startswith("https://panel.example.com/ejemplo/")
    assert all(body["to"] == VISITOR for body in sent)

    world.chat("Me interesa la primera")
    buttons = world.graph.sent()[-1]["interactive"]["action"]["buttons"]
    assert 1 <= len(buttons) <= 3
    assert all(len(button["reply"]["title"]) <= 20 for button in buttons)


def test_long_texts_are_split(world: World) -> None:
    from followup_core.messaging.domain.outbound import text_bodies

    bodies = text_bodies("línea\n" * 1200)
    assert len(bodies) == 2
    assert all(len(body["text"]["body"]) <= 4096 for body in bodies)


@pytest.mark.parametrize(("status", "code"), [(429, 130429), (503, 1), (500, 2)])
def test_429_and_5xx_are_retried_without_sending_twice(
    world: World, status: int, code: int
) -> None:
    world.graph.fail_next = [(status, code)]
    world.chat("Hola")
    assert world.jobs("whatsapp.send") == [("failed", 1)]
    assert world.outbound() == [("queued", None, None)]

    world.run(after_seconds=30)
    assert world.jobs("whatsapp.send") == [("done", 2)]
    assert world.outbound() == [("queued", "wamid.out.1", None)]
    assert world.graph.accepted == 1


def test_a_permanent_error_marks_the_part_failed_with_its_code(world: World) -> None:
    world.graph.fail_next = [(400, 131026)]
    world.chat("Hola")

    assert world.outbound() == [("failed", None, "131026")]
    assert world.jobs("whatsapp.send") == [("done", 1)]


def test_status_updates_move_the_delivery_forward_only(world: World) -> None:
    world.chat("Hola")
    wamid = world.outbound()[0][1]
    assert wamid is not None

    for status in ("delivered", "sent", "read", "delivered"):
        world.post(simulate_whatsapp.status_payload(wamid, status, phone_number_id=PHONE_NUMBER_ID))
    assert world.outbound()[0][0] == "read"

    (lead,) = world.owner.get("/leads").json()["items"]
    transcript = world.owner.get(f"/leads/{lead['id']}").json()["transcript"]
    assert [m["delivery_status"] for m in transcript] == [None, "read"]


def test_outside_the_24_hour_window_free_text_is_refused(world: World) -> None:
    world.say("Hola")
    world.clock.advance(seconds=5)
    world.runner.run_next()  # only the processing job
    world.execute(
        "UPDATE conversation_messages SET created_at = created_at - interval '25 hours' "
        "WHERE direction = 'inbound'"
    )
    world.run()

    assert world.outbound() == [("failed", None, "outside_service_window")]
    assert world.graph.sent() == []


# --- Emails ---------------------------------------------------------------------------------


def test_one_hand_off_email_per_lead_to_the_notification_emails(world: World) -> None:
    world.chat("Hola", "Quiero hablar con una persona", "¿Hay alguien?", "Hola?")

    (email,) = world.emails.sent
    setup = world.owner.get("/agent-setup").json()
    assert list(email.to) == setup["notification_emails"]
    assert email.subject.startswith("Nueva consulta: +54 9 11 5555-0188")
    assert "Pidió hablar con alguien" in email.text
    assert "https://panel.example.com/consultas?lead=" in email.text
    assert email.html and "Ver la consulta" in email.html


def test_the_in_progress_email_goes_only_without_a_hand_off(client, auth, database) -> None:
    world = _world(client, auth, database)
    world.chat("Hola", "Quiero alquilar")
    world.chat("Hola", "Quiero hablar con alguien", sender="5493515550000")
    assert [email.subject.split(":")[0] for email in world.emails.sent] == ["Nueva consulta"]

    world.run(after_seconds=16 * 60)
    world.run(after_seconds=16 * 60)

    in_progress = [e for e in world.emails.sent if e.subject.startswith("Consulta en curso")]
    assert [email.subject for email in in_progress] == [
        "Consulta en curso: +54 9 11 5555-0188 · Alquiler"
    ]
    assert len(world.emails.sent) == 2
    app.dependency_overrides.pop(get_messaging_services, None)


def test_simulator_leads_never_send_emails(world: World) -> None:
    for message in ["Hola", "Quiero hablar con una persona"]:
        world.owner.post("/simulator/messages", {"text": message})
    world.run(after_seconds=16 * 60)

    assert world.emails.sent == []


# --- Connection (backoffice) ----------------------------------------------------------------


def test_connection_endpoints_are_admin_only_and_never_return_the_token(world: World) -> None:
    path = f"/admin/tenants/{world.owner.tenant_id}/whatsapp"
    assert world.owner.get(path).status_code == 403
    response = world.admin.get(path)

    assert response.status_code == 200
    assert "EAAG-secret-token" not in response.text
    body = response.json()
    assert (body["status"], body["has_access_token"], body["phone_number_id"]) == (
        "connected",
        True,
        PHONE_NUMBER_ID,
    )
    stored = world.sql("SELECT access_token_encrypted FROM whatsapp_connections")[0][0]
    assert stored.startswith("k1:") and "EAAG" not in stored


def test_test_subscribe_and_template_call_the_graph_api(world: World) -> None:
    path = f"/admin/tenants/{world.owner.tenant_id}/whatsapp"

    tested = world.client.post(f"{path}/test", headers=world.admin.headers).json()
    assert (tested["display_phone_number"], tested["verified_name"]) == (
        "+54 9 11 5555-0100",
        "Inmo Sur",
    )
    assert world.client.post(f"{path}/subscribe", headers=world.admin.headers).status_code == 200
    sent = world.client.post(
        f"{path}/test-message", json={"to": "11 5555-0188"}, headers=world.admin.headers
    )
    assert sent.status_code == 200

    calls = [(method, url.rsplit("/", 1)[-1]) for method, url, _ in world.graph.requests]
    assert ("GET", PHONE_NUMBER_ID) in calls and ("POST", "subscribed_apps") in calls
    template = world.graph.sent()[-1]
    assert template["to"] == "5491155550188"
    assert template["template"] == {"name": "hello_world", "language": {"code": "en_US"}}
    authorization = [
        request for request in world.graph.requests if request[1].endswith("/subscribed_apps")
    ]
    assert authorization


def test_graph_errors_mark_the_connection_and_show_the_meta_code(world: World) -> None:
    path = f"/admin/tenants/{world.owner.tenant_id}/whatsapp"
    world.graph.fail_next = [(401, 190)]

    response = world.client.post(
        f"{path}/test-message", json={"to": "11 5555-0188"}, headers=world.admin.headers
    )

    assert (response.status_code, response.json()) == (
        502,
        {"code": "whatsapp_api_error", "meta_code": "190"},
    )
    status = world.admin.get(path).json()
    assert (status["status"], status["last_error_code"]) == ("error", "190")


def test_a_number_belongs_to_one_business(world: World, client: TestClient, auth) -> None:
    other = Account(client, auth, "Otra inmobiliaria")

    taken = connect(client, world.admin.headers, other.tenant_id)
    invalid = connect(client, world.admin.headers, other.tenant_id, phone_number_id="no spaces!")

    assert (taken.status_code, taken.json()) == (409, {"code": "whatsapp_phone_number_taken"})
    assert (invalid.status_code, invalid.json()) == (422, {"code": "whatsapp_connection_invalid"})


def test_the_panel_sees_the_status_and_the_checklist_flips(world: World, db_session) -> None:
    _set_role(db_session, world.owner.user_id, "viewer")

    status = world.owner.get("/whatsapp").json()
    assert (status["status"], status["display_phone_number"]) == ("connected", "+54 9 11 5555-0100")
    assert "phone_number_id" not in status
    assert world.owner.get("/onboarding").json()["checklist"]["facts"]["whatsapp_connected"]

    world.client.post(
        f"/admin/tenants/{world.owner.tenant_id}/whatsapp/disconnect", headers=world.admin.headers
    )
    assert world.owner.get("/whatsapp").json()["status"] == "disconnected"
    assert not world.owner.get("/onboarding").json()["checklist"]["facts"]["whatsapp_connected"]


def test_a_disconnected_number_ignores_messages(world: World) -> None:
    world.client.post(
        f"/admin/tenants/{world.owner.tenant_id}/whatsapp/disconnect", headers=world.admin.headers
    )
    world.say("Hola")

    assert world.sql("SELECT status FROM whatsapp_inbound_events") == [("ignored",)]


# --- End to end with the log sender ------------------------------------------------------------


def test_path_a_with_the_log_sender(client: TestClient, auth, database) -> None:
    """The simulate script's payload → worker → agent → delivered → lead → email."""
    world = _world(client, auth, database, sender="log")
    world.chat("Hola, busco un 2 ambientes en Palermo", "Quiero alquilar", "Me interesa la primera")
    slot = world.sql(
        "SELECT payload FROM conversation_messages WHERE payload ? 'slots' ORDER BY seq DESC"
    )[0][0]["slots"][0]
    world.say(slot["label"], slot=slot["id"])
    world.run()
    world.chat("Me llamo Ana Pérez")
    world.run(after_seconds=10)  # the log sender's sent → delivered → read

    assert world.graph.requests == []  # nothing reached the Graph API
    assert {status for status, _, _ in world.outbound()} == {"read"}
    (lead,) = world.owner.get("/leads").json()["items"]
    assert (lead["status"], lead["is_test"]) == ("visit_proposed", False)
    (email,) = world.emails.sent
    assert email.subject.startswith("Nueva consulta: Ana Pérez · Alquiler")
    assert "Pidió visitar" in email.text
    app.dependency_overrides.pop(get_messaging_services, None)
