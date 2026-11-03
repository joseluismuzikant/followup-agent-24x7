"""The team's side of a lead (S6) end to end: takeover on both channels (also racing a
running turn), team replies, giving the conversation back, and confirming or cancelling the
visit inside and outside WhatsApp's 24-hour window."""

import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from followup_core.conversation.application.control import Actor
from followup_core.conversation.domain.llm import Extraction, ExtractionRequest
from followup_core.conversation.domain.thread import Author
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from inmo24x7_api.container import get_messaging_services, lead_actions
from inmo24x7_api.main import app
from test_setup_endpoints import Account, _set_role
from test_whatsapp import World, _world
from whatsapp_fakes import connect


class RecordingModel(FakeLanguageModel):
    """Records what the extractor reads; `hold` makes it wait (a turn that is running)."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[ExtractionRequest] = []
        self.hold: threading.Event | None = None
        self.entered = threading.Event()

    def extract(self, request: ExtractionRequest) -> Extraction:
        self.requests.append(request)
        if self.hold is not None:
            self.entered.set()
            assert self.hold.wait(10)
        return super().extract(request)


@pytest.fixture
def world(client: TestClient, auth, database):
    world = _world(client, auth, database, llm=RecordingModel())
    # The transcript names people by their display name.
    world.execute(
        "UPDATE profiles SET display_name = 'Luis' WHERE id = :id", id=world.owner.user_id
    )
    yield world
    app.dependency_overrides.pop(get_messaging_services, None)


def _handed_off(world: World) -> dict:
    """A WhatsApp lead that picked a slot and left a name: visit_proposed, handed off."""
    world.chat("Hola", "Quiero alquilar", "Palermo", "Me interesa la primera")
    slot = world.graph.sent()[-1]["interactive"]["action"]["buttons"][0]["reply"]
    world.say(slot["title"], slot=slot["id"])
    world.run()
    world.chat("Me llamo Ana Pérez")
    (lead,) = world.owner.get("/leads").json()["items"]
    return lead


def _detail(world: World, lead_id: str) -> dict:
    return world.owner.get(f"/leads/{lead_id}").json()


def _take_over(world: World, lead_id: str, account: Account | None = None):
    return (account or world.owner).post(f"/leads/{lead_id}/takeover", {})


def _agent_lines(world: World) -> list[str]:
    return [text for direction, author, text in world.transcript() if author == "agent"]


# --- Takeover -------------------------------------------------------------------------------


def test_takeover_pauses_the_agent_and_writes_a_system_event(world: World) -> None:
    lead = _handed_off(world)
    assert lead["needs_attention"] is True

    response = _take_over(world, lead["id"])

    assert response.status_code == 200
    detail = response.json()
    assert detail["control"]["mode"] == "human"
    assert detail["control"]["by"]["id"] == str(world.owner.user_id)
    assert detail["transcript"][-1]["author"] == "system"
    assert detail["transcript"][-1]["text"].endswith("tomó la conversación")

    agent_before, sent_before = _agent_lines(world), len(world.graph.sent())
    world.chat("¿Me confirman la visita?")

    assert _agent_lines(world) == agent_before
    assert len(world.graph.sent()) == sent_before
    assert world.transcript()[-1] == ("inbound", "visitor", "¿Me confirman la visita?")
    # The lead keeps its answers: a paused turn has no state to project.
    assert world.owner.get("/leads").json()["items"][0]["looking_for"].startswith("Alquiler")


def test_a_debounced_job_queued_before_the_takeover_does_not_answer(world: World) -> None:
    lead = _handed_off(world)
    agent_before = _agent_lines(world)
    world.say("Hola, ¿siguen ahí?")  # queued, still inside the debounce

    _take_over(world, lead["id"])
    world.run()

    assert _agent_lines(world) == agent_before
    assert world.transcript()[-1] == ("inbound", "visitor", "Hola, ¿siguen ahí?")


def test_media_under_takeover_gets_no_fixed_reply(world: World) -> None:
    lead = _handed_off(world)
    _take_over(world, lead["id"])
    sent_before = len(world.graph.sent())

    world.say(None, audio=True)
    world.run()

    assert world.transcript()[-1] == ("inbound", "visitor", "")
    assert len(world.graph.sent()) == sent_before


def test_a_takeover_waits_for_a_running_turn_and_later_turns_are_skipped(world: World) -> None:
    lead = _handed_off(world)
    model = world.llm
    assert isinstance(model, RecordingModel)
    model.hold, model.entered = threading.Event(), threading.Event()
    world.say("¿La visita sigue en pie?")
    turn = threading.Thread(target=world.run)
    turn.start()
    assert model.entered.wait(10)  # the turn holds the thread lock, inside the model call

    def take_over() -> None:
        with world.sessions() as session:
            actions = lead_actions(session, world.services)
            actions.take_over.execute(
                world.owner.tenant_id, UUID(lead["id"]), Actor(world.owner.user_id, "Luis")
            )
            session.commit()

    takeover = threading.Thread(target=take_over)
    takeover.start()
    time.sleep(0.3)
    assert takeover.is_alive()  # blocked on the lock until the turn commits

    model.hold.set()
    turn.join(10)
    takeover.join(10)
    model.hold = None

    authors = [author for _, author, _ in world.transcript()]
    # The running turn finished (its reply is stored) before the takeover's event.
    assert authors[-3:] == ["visitor", "agent", "system"]
    world.chat("Hola?")
    assert world.transcript()[-1] == ("inbound", "visitor", "Hola?")


def test_taking_over_from_someone_else_moves_control(world: World, client, auth) -> None:
    lead = _handed_off(world)
    _take_over(world, lead["id"])
    colleague = Account(client, auth, "Otra")
    world.execute(
        "UPDATE profiles SET tenant_id = :t WHERE id = :id",
        t=world.owner.tenant_id,
        id=colleague.user_id,
    )

    detail = _take_over(world, lead["id"], colleague).json()

    assert detail["control"]["by"]["id"] == str(colleague.user_id)
    events = [m["text"] for m in detail["transcript"] if m["author"] == "system"]
    assert sum(text.endswith("tomó la conversación") for text in events) == 2


def test_viewers_read_but_cannot_act(world: World, db_session) -> None:
    lead = _handed_off(world)
    _set_role(db_session, world.owner.user_id, "viewer")

    assert world.owner.get(f"/leads/{lead['id']}").status_code == 200
    for path, body in (
        (f"/leads/{lead['id']}/takeover", {}),
        (f"/leads/{lead['id']}/release", {}),
        (f"/leads/{lead['id']}/messages", {"text": "Hola"}),
    ):
        response = world.owner.post(path, body)
        assert (response.status_code, response.json()["code"]) == (403, "forbidden")


def test_another_tenant_cannot_see_or_take_the_lead(world: World, client, auth) -> None:
    lead = _handed_off(world)
    stranger = Account(client, auth, "Otra inmobiliaria")

    assert stranger.get(f"/leads/{lead['id']}").status_code == 404
    response = _take_over(world, lead["id"], stranger)
    assert (response.status_code, response.json()["code"]) == (404, "lead_not_found")


# --- Team replies ---------------------------------------------------------------------------


def test_a_reply_needs_the_conversation_taken(world: World) -> None:
    lead = _handed_off(world)

    response = world.owner.post(f"/leads/{lead['id']}/messages", {"text": "Hola Ana"})

    assert (response.status_code, response.json()["code"]) == (409, "conversation_not_taken")


def test_a_whatsapp_reply_is_sent_by_the_send_job(world: World) -> None:
    lead = _handed_off(world)
    _take_over(world, lead["id"])

    response = world.owner.post(f"/leads/{lead['id']}/messages", {"text": "Hola Ana, soy Luis"})

    assert response.status_code == 201
    message = response.json()
    assert (message["author"], message["author_name"]) == ("human", "Luis")
    world.run()
    assert world.graph.sent()[-1]["text"]["body"] == "Hola Ana, soy Luis"
    # Accepted by Meta (a wamid); "sent" arrives later as a status webhook.
    assert world.outbound()[-1][1] is not None
    detail = _detail(world, lead["id"])
    # Someone answered: the lead leaves "Para atender".
    assert detail["needs_attention"] is False
    assert world.owner.get("/leads?tab=attention").json()["counts"]["attention"] == 0


def test_outside_the_window_a_reply_is_refused_and_nothing_is_stored(world: World) -> None:
    lead = _handed_off(world)
    _take_over(world, lead["id"])
    world.execute(
        "UPDATE conversation_messages SET created_at = created_at - interval '25 hours' "
        "WHERE author = 'visitor'"
    )
    before = world.transcript()

    response = world.owner.post(f"/leads/{lead['id']}/messages", {"text": "Hola"})

    assert (response.status_code, response.json()["code"]) == (409, "outside_service_window")
    assert world.transcript() == before
    window = _detail(world, lead["id"])["service_window"]
    assert window["open"] is False


def test_the_detail_shows_the_window_expiry(world: World) -> None:
    lead = _handed_off(world)

    window = _detail(world, lead["id"])["service_window"]

    assert window["open"] is True
    expires = datetime.fromisoformat(window["expires_at"])
    assert timedelta(hours=23) < expires - datetime.now(UTC) <= timedelta(hours=24)


def test_release_resumes_the_agent_with_the_teams_messages(world: World) -> None:
    world.chat("Hola")
    (lead,) = world.owner.get("/leads").json()["items"]
    _take_over(world, lead["id"])
    world.owner.post(f"/leads/{lead['id']}/messages", {"text": "¿Cuál es tu presupuesto?"})
    world.run()
    world.chat("Hasta 900 mil pesos")

    released = world.owner.post(f"/leads/{lead['id']}/release", {}).json()
    assert (released["control"]["mode"], released["control"]["by"]) == ("agent", None)
    assert released["transcript"][-1]["text"].endswith("devolvió la conversación al agente")
    world.chat("Quiero alquilar")

    model = world.llm
    assert isinstance(model, RecordingModel)
    request = model.requests[-1]
    assert (Author.HUMAN, "¿Cuál es tu presupuesto?") in [
        (line.author, line.text) for line in request.transcript
    ]
    # What the lead told the team reaches the agent with the new message.
    assert request.latest == "Hasta 900 mil pesos\nQuiero alquilar"
    answers = {row["key"]: row["value"] for row in _detail(world, lead["id"])["answers"]}
    assert answers["budget"] == "Hasta $900.000"
    assert answers["operation"] == "Alquiler"


# --- Confirm and cancel the visit ------------------------------------------------------------


def test_confirming_inside_the_window_sends_text_and_leaves_attention(world: World) -> None:
    lead = _handed_off(world)
    (visit,) = _detail(world, lead["id"])["visits"]

    response = world.owner.post(f"/leads/{lead['id']}/visits/{visit['id']}/confirm", {})

    assert response.status_code == 200
    detail = response.json()
    assert detail["status"] == "visit_confirmed"
    assert detail["visits"][0]["status"] == "confirmed"
    assert detail["needs_attention"] is False
    system, confirmation = detail["transcript"][-2:]
    assert (system["author"], system["text"]) == ("system", "Luis confirmó la visita")
    assert confirmation["author"] == "human"
    assert confirmation["text"].startswith("¡Listo, Ana! Te confirmamos la visita a ")
    world.run()
    assert world.graph.sent()[-1]["text"]["body"] == confirmation["text"]

    again = world.owner.post(f"/leads/{lead['id']}/visits/{visit['id']}/confirm", {}).json()
    assert len(again["transcript"]) == len(detail["transcript"])


def test_confirming_can_change_the_time_but_not_to_the_past(world: World) -> None:
    lead = _handed_off(world)
    (visit,) = _detail(world, lead["id"])["visits"]
    path = f"/leads/{lead['id']}/visits/{visit['id']}/confirm"
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    refused = world.owner.post(path, {"starts_at": past})
    assert (refused.status_code, refused.json()["code"]) == (422, "visit_time_in_past")

    later = datetime(2030, 11, 9, 13, 30, tzinfo=UTC)  # sábado 9/11, 10:30 in Buenos Aires
    detail = world.owner.post(path, {"starts_at": later.isoformat()}).json()

    assert datetime.fromisoformat(detail["visits"][0]["starts_at"]) == later
    assert "el sábado 9/11 a las 10:30" in detail["transcript"][-1]["text"]


def _outside_window(world: World) -> None:
    world.execute(
        "UPDATE conversation_messages SET created_at = created_at - interval '2 days' "
        "WHERE author = 'visitor'"
    )


def test_outside_the_window_without_a_template_nothing_changes(world: World) -> None:
    lead = _handed_off(world)
    (visit,) = _detail(world, lead["id"])["visits"]
    _outside_window(world)
    before = _detail(world, lead["id"])

    response = world.owner.post(f"/leads/{lead['id']}/visits/{visit['id']}/confirm", {})

    assert (response.status_code, response.json()["code"]) == (409, "template_not_configured")
    after = _detail(world, lead["id"])
    assert (after["status"], after["visits"], after["transcript"]) == (
        before["status"],
        before["visits"],
        before["transcript"],
    )


def test_outside_the_window_the_template_goes_with_its_parameters(world: World) -> None:
    lead = _handed_off(world)
    (visit,) = _detail(world, lead["id"])["visits"]
    response = connect(
        world.client,
        world.admin.headers,
        world.owner.tenant_id,
        visit_template_name="confirmacion_visita",
    )
    assert response.json()["visit_template_name"] == "confirmacion_visita"
    _outside_window(world)

    detail = world.owner.post(f"/leads/{lead['id']}/visits/{visit['id']}/confirm", {}).json()
    world.run()

    assert detail["status"] == "visit_confirmed"
    body = world.graph.sent()[-1]
    assert body["type"] == "template"
    template = body["template"]
    assert (template["name"], template["language"]["code"]) == ("confirmacion_visita", "es_AR")
    name, address, when = [p["text"] for p in template["components"][0]["parameters"]]
    assert name == "Ana"
    assert address and " a las " in when
    # Templates go out even outside the window.
    assert world.outbound()[-1][1] is not None


def test_cancelling_goes_back_to_human_requested(world: World) -> None:
    lead = _handed_off(world)
    (visit,) = _detail(world, lead["id"])["visits"]

    detail = world.owner.post(
        f"/leads/{lead['id']}/visits/{visit['id']}/cancel",
        {"message": "Perdón Ana, se cayó la visita. ¿Te viene bien otro día?"},
    ).json()
    world.run()

    assert detail["status"] == "human_requested"
    assert detail["visits"][0]["status"] == "cancelled"
    assert detail["transcript"][-2]["text"] == "Luis canceló la visita"
    assert world.graph.sent()[-1]["text"]["body"].startswith("Perdón Ana")


def test_cancelling_with_a_message_outside_the_window_is_refused(world: World) -> None:
    lead = _handed_off(world)
    (visit,) = _detail(world, lead["id"])["visits"]
    _outside_window(world)
    path = f"/leads/{lead['id']}/visits/{visit['id']}/cancel"

    refused = world.owner.post(path, {"message": "Se cayó la visita"})
    assert (refused.status_code, refused.json()["code"]) == (409, "outside_service_window")
    assert world.owner.post(path, {}).json()["visits"][0]["status"] == "cancelled"


def test_unknown_visits_and_cancelled_ones(world: World) -> None:
    lead = _handed_off(world)
    (visit,) = _detail(world, lead["id"])["visits"]
    world.owner.post(f"/leads/{lead['id']}/visits/{visit['id']}/cancel", {})

    unknown = world.owner.post(f"/leads/{lead['id']}/visits/{lead['id']}/confirm", {})
    cancelled = world.owner.post(f"/leads/{lead['id']}/visits/{visit['id']}/confirm", {})

    assert (unknown.status_code, unknown.json()["code"]) == (404, "visit_not_found")
    assert (cancelled.status_code, cancelled.json()["code"]) == (409, "visit_cancelled")


# --- The simulator ---------------------------------------------------------------------------


def _simulator_lead(owner: Account) -> dict:
    for text in ("Hola", "Quiero alquilar", "Palermo", "Me interesa la primera"):
        reply = owner.post("/simulator/messages", {"text": text}).json()
    slot = reply["messages"][-1]["slots"][0]
    owner.post("/simulator/messages", {"text": slot["label"], "choice_id": slot["id"]})
    owner.post("/simulator/messages", {"text": "Me llamo Ana Pérez, 11 5555-0188"})
    (lead,) = owner.get("/leads?include_test=true").json()["items"]
    return lead


def test_takeover_and_confirmation_in_the_simulator(world: World) -> None:
    owner = world.owner
    lead = _simulator_lead(owner)
    _take_over(world, lead["id"])

    reply = owner.post("/simulator/messages", {"text": "¿Hay alguien?"}).json()
    assert reply["messages"] == []
    assert owner.post(f"/leads/{lead['id']}/messages", {"text": "Sí, acá estoy"}).status_code == 201
    (visit,) = _detail(world, lead["id"])["visits"]
    owner.post(f"/leads/{lead['id']}/visits/{visit['id']}/confirm", {})

    simulator = owner.get("/simulator").json()
    assert simulator["control"] == "human"
    texts = [(m["author"], m["text"]) for m in simulator["messages"]]
    assert ("human", "Sí, acá estoy") in texts
    assert texts[-1][1].startswith("¡Listo, Ana! Te confirmamos la visita")
    assert world.graph.sent() == []  # nothing leaves the simulator
    assert world.outbound() == []
