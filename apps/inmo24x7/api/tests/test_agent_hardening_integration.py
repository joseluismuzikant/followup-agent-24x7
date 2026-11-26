"""Phase 1 hardening against the test database: the checkpointer (PostgresSaver), an old
checkpoint under the new graph, and WhatsApp through the pipeline (answer plus step, "BAJA"
first, the model down on the job's last attempt). Nothing reaches Meta or a model."""

from typing import Any

import psycopg
from conftest import TEST_DATABASE_URL
from fastapi.testclient import TestClient
from followup_core.conversation.domain.errors import LlmUnavailableError
from followup_core.conversation.domain.runtime import TurnInput
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from followup_core.messaging.domain.opt_out import OPT_OUT_CONFIRMATION
from inmo24x7_api.container import (
    agent_runtime,
    get_messaging_services,
    send_simulator_message_use_case,
)
from inmo24x7_api.leads.graph import LeadState
from inmo24x7_api.leads.safe_texts import AGENT_FAILURE_TEXT
from inmo24x7_api.main import app
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_setup_endpoints import Account
from test_whatsapp import _world


def _simulate(account: Account, text: str) -> dict:
    response = account.post("/simulator/messages", {"text": text})
    assert response.status_code == 200, response.json()
    return response.json()


def _agent_texts(body: dict) -> list[str]:
    return [m["text"] for m in body["messages"] if m["author"] == "agent"]


# --- The checkpointer ------------------------------------------------------------------------


def test_answers_refines_and_progress_persist_through_postgres(client: TestClient, auth) -> None:
    owner = Account(client, auth)  # conftest runs the API on the fake model
    for text in ["Hola", "Quiero alquilar", "Palermo"]:
        _simulate(owner, text)
    before = len(_agent_texts(owner.get("/simulator").json()))

    _simulate(owner, "¿cuál es la más barata?")
    _simulate(owner, "¿y en Caballito?")
    body = owner.get("/simulator").json()  # the whole thread, read back from the database

    texts = _agent_texts(body)
    assert texts[before].startswith("La más barata es la ")
    assert {row["key"]: row["value"] for row in body["known"]}["zone"] == "Caballito"


def _old_graph() -> StateGraph[Any, Any, Any, Any]:
    """The graph before phase 1: START -> extract -> respond -> END, and a state without
    the new keys (and a name the new rules reject)."""

    def extract(state: LeadState) -> dict[str, Any]:
        return {}

    def respond(state: LeadState) -> dict[str, Any]:
        return {
            "outbox": [{"text": "¡Hola! Soy Sofía.", "payload": None}],
            "answers": {"operation": "alquiler"},
            "visitor_name": "Ana " * 15,
            "asked_key": "zone",
            "last_intent": "ask",
            "turns": 2,
        }

    graph = StateGraph(LeadState)
    graph.add_node("extract", extract)
    graph.add_node("respond", respond)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "respond")
    graph.add_edge("respond", END)
    return graph


def test_an_old_checkpoint_resumes_under_the_new_graph(client: TestClient, auth) -> None:
    account = Account(client, auth)
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with Session(engine) as session:
            use_case = send_simulator_message_use_case(
                session,
                agent_runtime(session, FakeLanguageModel(), tracing=None, usage=None),
                daily_limit=300,
            )
            turn = use_case.execute(account.tenant_id, account.user_id, "Hola")
            session.commit()
            key = turn.thread.key
            connection = session.connection().connection.driver_connection
            assert isinstance(connection, psycopg.Connection)
            old = _old_graph().compile(checkpointer=PostgresSaver(connection))
            old.invoke(
                {"inbound": "Quiero alquilar", "outbox": []},
                {"configurable": {"thread_id": str(key)}},
                durability="exit",
            )
            session.commit()

        with Session(engine) as session:
            runtime = agent_runtime(session, FakeLanguageModel(), tracing=None, usage=None)
            use_case = send_simulator_message_use_case(session, runtime, daily_limit=300)
            resumed = use_case.execute(account.tenant_id, account.user_id, "Palermo")
            session.commit()
    finally:
        engine.dispose()

    state = resumed.state
    assert state["turns"] == 3
    assert state["answers"]["zone"] == "Palermo"
    assert state.get("visitor_name") is None  # the old, too long name is dropped
    assert state["progress"]["stage"] == "options_shown"
    assert resumed.termination_reason == "completed"


# --- WhatsApp ----------------------------------------------------------------------------------


def _bodies(world) -> list[str]:
    return [
        body.get("text", {}).get("body", "") or str(body.get("interactive", ""))
        for body in world.graph.sent()
    ]


def test_an_answer_and_the_next_step_go_out_in_order(client, auth, database) -> None:
    world = _world(client, auth, database)
    try:
        world.chat("Hola", "Quiero alquilar", "Palermo")
        before = len(world.graph.sent())

        world.chat("¿cuál es la más barata?")

        answer, step = _bodies(world)[before:]
        assert answer.startswith("La más barata es la ")
        assert "?" in step and "?" not in answer
    finally:
        app.dependency_overrides.pop(get_messaging_services, None)


def test_baja_is_still_answered_before_the_agent(client, auth, database) -> None:
    world = _world(client, auth, database)
    try:
        world.chat("Hola")
        before = len(world.graph.sent())

        world.chat("BAJA")

        assert _bodies(world)[before:] == [OPT_OUT_CONFIRMATION]
    finally:
        app.dependency_overrides.pop(get_messaging_services, None)


def test_the_model_down_on_the_last_attempt_hands_off_instead_of_dying(
    client, auth, database
) -> None:
    llm = FakeLanguageModel(fail_with=LlmUnavailableError("down"))
    world = _world(client, auth, database, llm=llm)
    try:
        world.say("Hola, busco alquilar en Palermo")
        world.execute("UPDATE jobs SET max_attempts = 3 WHERE kind = 'whatsapp.process'")
        for _ in range(3):
            world.run(after_seconds=120)

        assert world.jobs("whatsapp.process") == [("done", 3)]
        assert _bodies(world) == [AGENT_FAILURE_TEXT]
        (lead,) = world.owner.get("/leads").json()["items"]
        assert (lead["status"], lead["hand_off_reason"]) == ("human_requested", "agent_failure")
        assert world.sql(
            "SELECT details->>'code' FROM audit_events WHERE action = 'agent_failure_hand_off'"
        ) == [("provider_unavailable",)]
        assert len(world.emails.sent) == 1
        assert "no estaba disponible" in world.emails.sent[0].text
    finally:
        app.dependency_overrides.pop(get_messaging_services, None)


def test_turn_input_carries_the_final_attempt() -> None:
    assert TurnInput.__dataclass_fields__["final_attempt"].default is False
