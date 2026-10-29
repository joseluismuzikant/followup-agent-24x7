"""LangSmith tracing: PII redaction, run naming and metadata, and that tracing can never
break a turn. Nothing here touches the network."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from followup_core.conversation.domain.runtime import BusinessContext, TurnInput
from followup_core.conversation.domain.thread import Channel, Thread, ThreadKey, ThreadStatus
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from followup_core.conversation.infrastructure.langgraph_runtime import LangGraphRuntime
from inmo24x7_api.config import Settings
from inmo24x7_api.container import get_trace_ui_url, get_turn_tracing
from inmo24x7_api.defaults import build_setup_defaults
from inmo24x7_api.leads.graph import build_lead_graph
from inmo24x7_api.leads.properties import SamplePropertySearch
from inmo24x7_api.main import app
from inmo24x7_api.tracing import (
    anonymize,
    build_tracing,
    project_name,
    trace_url,
    turn_tracing,
)
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import text
from test_setup_endpoints import Account
from tracing_fakes import RecordingClient, recording_tracing

# --- Anonymizer ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phone",
    [
        "+54 9 11 1234-5678",
        "+5491123456789",
        "011 15 1234-5678",
        "(0351) 456-7890",
        "11 2345 6789",
        "1123456789",
        "15-4567-8901",
    ],
)
def test_anonymizer_masks_argentine_phone_numbers(phone: str) -> None:
    masked = anonymize({"text": f"llamame al {phone} después de las 18"})["text"]

    assert masked == "llamame al <phone> después de las 18"


@pytest.mark.parametrize("dni", ["30.123.456", "7.654.321", "30123456"])
def test_anonymizer_masks_dni_like_numbers(dni: str) -> None:
    masked = anonymize({"text": f"mi DNI es {dni}."})["text"]

    assert masked.startswith("mi DNI es <")
    assert not any(char.isdigit() for char in masked)


def test_anonymizer_masks_emails_in_nested_structures() -> None:
    data = {
        "messages": [{"content": "soy ana.perez+casa@gmail.com"}],
        "state": {"contact": "ventas@inmo-sur.com.ar"},
    }

    masked = anonymize(data)

    assert masked["messages"][0]["content"] == "soy <email>"
    assert masked["state"]["contact"] == "<email>"


def test_anonymizer_keeps_prices_dates_and_ids() -> None:
    kept = (
        "presupuesto $900.000 o USD 120000, 3 ambientes, 2026-10-29T13:37:22, "
        "8861a004-25f2-4b0f-93dd-41aa1a5e0805:simulator:00000000-0000-0000-0000-000000000001.1"
    )

    assert anonymize({"text": kept})["text"] == kept


# --- Settings ----------------------------------------------------------------------------


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "development",
        "database_url": "postgresql+psycopg://db/app",
        "cors_origins": (),
        "version": "1.2.3",
        "commit": "abc",
        "build_date": "today",
        "supabase_url": "",
        "supabase_jwt_secret": "",
        "supabase_jwks_url": "",
    }
    values.update(overrides)
    return Settings(**values)


def test_tracing_is_off_by_default_and_without_a_key() -> None:
    assert build_tracing(_settings()) is None
    assert build_tracing(_settings(langsmith_tracing=True)) is None


def test_tracing_client_redacts_pii_unless_disabled() -> None:
    on = build_tracing(_settings(langsmith_tracing=True, langsmith_api_key="lsv2-test"))
    off = build_tracing(
        _settings(langsmith_tracing=True, langsmith_api_key="lsv2-test", langsmith_redact_pii=False)
    )

    assert on is not None and off is not None
    # The client masks inputs and outputs itself before posting any run.
    run = {"text": "ana@example.com, +54 9 11 1234-5678"}
    assert on.client._hide_run_inputs(dict(run)) == {"text": "<email>, <phone>"}
    assert on.client._hide_run_outputs(dict(run)) == {"text": "<email>, <phone>"}
    assert off.client._hide_run_inputs(dict(run)) == run
    assert on.project_name == "inmo24x7-dev"


def test_project_name_per_environment() -> None:
    assert project_name(_settings(app_env="production")) == "inmo24x7-prod"
    assert project_name(_settings(langsmith_project="custom")) == "custom"


def test_trace_url_needs_the_ui_url_and_a_run_id() -> None:
    run_id = uuid4()

    assert trace_url("", run_id) is None
    assert trace_url("https://smith.example/o/1/projects/p/2", None) is None
    assert trace_url("https://smith.example/o/1/projects/p/2", run_id) == (
        f"https://smith.example/o/1/projects/p/2/r/{run_id}?poll=true"
    )


# --- Runs ---------------------------------------------------------------------------------


def _runtime(client: RecordingClient) -> tuple[LangGraphRuntime, Thread, TurnInput]:
    tenant_id = uuid4()
    runtime = LangGraphRuntime(
        build_lead_graph(SamplePropertySearch()),
        InMemorySaver(),
        FakeLanguageModel(),
        recording_tracing(client),
    )
    thread = Thread(
        uuid4(),
        ThreadKey(tenant_id, Channel.SIMULATOR, "visitor.1"),
        3,
        ThreadStatus.OPEN,
        datetime.now(UTC),
        None,
    )
    turn = TurnInput(
        build_setup_defaults().agent_config,
        BusinessContext(tenant_id, "Inmobiliaria Sur", "UTC"),
        [],
        "Hola, quiero alquilar en Palermo",
    )
    return runtime, thread, turn


def test_a_turn_is_one_named_run_with_tags_metadata_and_child_runs() -> None:
    client = RecordingClient()
    runtime, thread, turn = _runtime(client)

    result = runtime.handle(thread, turn)

    (root,) = client.named("inmo24x7.lead_turn")
    assert result.trace_run_id is not None
    assert str(root["id"]) == str(result.trace_run_id)
    assert {"inmo24x7", "development", "simulator"} <= set(root["tags"])
    metadata = root["extra"]["metadata"]
    assert metadata["tenant_id"] == str(thread.tenant_id)
    assert metadata["thread_key"] == str(thread.key)
    assert metadata["channel"] == "simulator"
    assert metadata["agent_config_version"] == 3
    assert metadata["prompt_versions"] == {"extract": "fake", "reply": "fake"}
    assert (metadata["app_version"], metadata["commit"]) == ("9.9.9", "abc123")
    for name in ("llm.extract", "llm.compose_reply", "property_search"):
        children = client.named(name)
        assert children, name
        assert all(str(child["trace_id"]) == str(result.trace_run_id) for child in children)


def test_a_failing_tracer_does_not_fail_the_turn() -> None:
    runtime, thread, turn = _runtime(RecordingClient(fail=True))

    result = runtime.handle(thread, turn)

    assert result.outbound
    assert result.state["answers"]["operation"] == "alquiler"


def test_without_tracing_nothing_is_recorded_and_there_is_no_run_id() -> None:
    client = RecordingClient()
    runtime, thread, turn = _runtime(client)
    untraced = LangGraphRuntime(
        build_lead_graph(SamplePropertySearch()), InMemorySaver(), FakeLanguageModel()
    )

    result = untraced.handle(thread, turn)

    assert result.trace_run_id is None
    assert client.named("inmo24x7.lead_turn") == []


def test_turn_tracing_carries_the_product_settings() -> None:
    tracing = build_tracing(_settings(langsmith_tracing=True, langsmith_api_key="lsv2-test"))
    settings = _settings(version="1.2.3", commit="abc")

    configured = turn_tracing(tracing, settings)

    assert configured is not None
    assert configured.run_name == "inmo24x7.lead_turn"
    assert tuple(configured.tags) == ("inmo24x7", "development")
    assert dict(configured.metadata) == {"app_version": "1.2.3", "commit": "abc"}
    assert turn_tracing(None, settings) is None


# --- Stored run id and the backoffice link -----------------------------------------------


def test_the_run_id_is_stored_on_outbound_messages(client: TestClient, auth, db_session) -> None:
    owner = Account(client, auth)
    admin = Account(client, auth, "Plataforma")
    auth.make_admin(admin.user_id)
    recording = RecordingClient()
    app.dependency_overrides[get_turn_tracing] = lambda: recording_tracing(recording)
    app.dependency_overrides[get_trace_ui_url] = lambda: "https://smith.example/o/1/projects/p/2"
    try:
        tenant_reply = owner.post("/simulator/messages", {"text": "Hola"}).json()
        path = f"/admin/tenants/{owner.tenant_id}/simulator"
        admin_reply = admin.post(f"{path}/messages", {"text": "Hola"}).json()
        admin_view = admin.get(path).json()
    finally:
        app.dependency_overrides.pop(get_turn_tracing)
        app.dependency_overrides.pop(get_trace_ui_url)

    rows = db_session.execute(
        text("SELECT direction, trace_run_id FROM conversation_messages ORDER BY seq")
    ).all()
    outbound = [row.trace_run_id for row in rows if row.direction == "outbound"]
    inbound = [row.trace_run_id for row in rows if row.direction == "inbound"]
    assert len(outbound) == 2 and all(isinstance(run_id, UUID) for run_id in outbound)
    assert inbound == [None, None]
    roots = {str(run["id"]) for run in recording.named("inmo24x7.lead_turn")}
    assert {str(run_id) for run_id in outbound} == roots
    # The link is backoffice-only.
    assert tenant_reply["messages"][0]["trace_url"] is None
    link = admin_reply["messages"][0]["trace_url"]
    assert link.startswith("https://smith.example/o/1/projects/p/2/r/")
    assert [m["trace_url"] is not None for m in admin_view["messages"]] == [False, True]


def test_no_link_without_the_ui_url(client: TestClient, auth) -> None:
    owner = Account(client, auth)
    admin = Account(client, auth, "Plataforma")
    auth.make_admin(admin.user_id)
    recording = RecordingClient()
    app.dependency_overrides[get_turn_tracing] = lambda: recording_tracing(recording)
    try:
        path = f"/admin/tenants/{owner.tenant_id}/simulator"
        reply = admin.post(f"{path}/messages", {"text": "Hola"}).json()
    finally:
        app.dependency_overrides.pop(get_turn_tracing)

    assert reply["messages"][0]["trace_url"] is None
