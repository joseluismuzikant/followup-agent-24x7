"""The conversation survives an API restart, and turns on one thread never interleave.

Both tests build the use cases the way the container does, but on engines they own, so they
can drop every connection (a restart) or run two requests at once.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from conftest import TEST_DATABASE_URL
from fastapi.testclient import TestClient
from followup_core.conversation.domain.llm import Extraction, ExtractionRequest
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from inmo24x7_api.container import agent_runtime, send_simulator_message_use_case
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_setup_endpoints import Account


def _send(engine: Engine, account: Account, text: str, llm: FakeLanguageModel) -> dict:
    with Session(engine) as session:
        use_case = send_simulator_message_use_case(
            session, agent_runtime(session, llm, tracing=None), daily_limit=300
        )
        turn = use_case.execute(account.tenant_id, account.user_id, text)
        session.commit()
        return dict(turn.state)


def test_conversation_continues_after_a_restart(client: TestClient, auth) -> None:
    account = Account(client, auth)
    llm = FakeLanguageModel()

    first_engine = create_engine(TEST_DATABASE_URL)
    _send(first_engine, account, "Hola", llm)
    before = _send(first_engine, account, "Quiero alquilar", llm)
    first_engine.dispose()  # the API process stops: no connection, no in-memory state

    second_engine = create_engine(TEST_DATABASE_URL)
    try:
        after = _send(second_engine, account, "Palermo", FakeLanguageModel())
    finally:
        second_engine.dispose()

    assert before["answers"] == {"operation": "alquiler"}
    assert after["answers"] == {"operation": "alquiler", "zone": "Palermo"}
    assert after["turns"] == 3
    body = account.get("/simulator").json()
    inbound = [m["text"] for m in body["messages"] if m["direction"] == "inbound"]
    assert inbound == ["Hola", "Quiero alquilar", "Palermo"]
    assert {row["key"]: row["value"] for row in body["known"]}["zone"] == "Palermo"


class SlowLlm(FakeLanguageModel):
    """Holds each extraction for a while and records how many turns run at once."""

    def __init__(self) -> None:
        super().__init__()
        self._guard = threading.Lock()
        self.active = 0
        self.max_active = 0

    def extract(self, request: ExtractionRequest) -> Extraction:
        with self._guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.3)
        with self._guard:
            self.active -= 1
        return super().extract(request)


def test_simultaneous_messages_on_one_thread_run_one_after_the_other(
    client: TestClient, auth
) -> None:
    account = Account(client, auth)
    llm = SlowLlm()
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda text: _send(engine, account, text, llm), ["Hola", "Quiero alquilar"]
                )
            )
    finally:
        engine.dispose()

    assert llm.max_active == 1
    assert sorted(state["turns"] for state in results) == [1, 2]
    body = account.get("/simulator").json()
    directions = [m["direction"] for m in body["messages"]]
    # in, out, in, out(s): the second turn starts only after the first one is stored.
    assert directions[:3] == ["inbound", "outbound", "inbound"]
    assert directions.count("inbound") == 2
    assert body["thread"]["key"].endswith(f"{account.user_id}.1")
