"""A LangSmith client that records runs instead of sending them (no network)."""

from typing import Any

from followup_core.conversation.infrastructure.langgraph_runtime import TurnTracing
from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import Client


class RecordingClient(Client):
    def __init__(self, fail: bool = False) -> None:
        super().__init__(api_key="test-key", api_url="http://127.0.0.1:9", auto_batch_tracing=False)
        self.fail = fail
        self.recorded: dict[str, dict[str, Any]] = {}

    def create_run(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        if self.fail:
            raise RuntimeError("LangSmith is down")
        self.recorded[str(kwargs["id"])] = dict(kwargs)

    def update_run(self, run_id: Any, **kwargs: Any) -> None:  # type: ignore[override]
        if self.fail:
            raise RuntimeError("LangSmith is down")
        self.recorded.setdefault(str(run_id), {}).update(kwargs)

    def named(self, name: str) -> list[dict[str, Any]]:
        wait_for_all_tracers()
        return [run for run in self.recorded.values() if run.get("name") == name]


def recording_tracing(client: RecordingClient) -> TurnTracing:
    return TurnTracing(
        client=client,
        project_name="inmo24x7-test",
        run_name="inmo24x7.lead_turn",
        tags=("inmo24x7", "development"),
        metadata={"app_version": "9.9.9", "commit": "abc123"},
    )
