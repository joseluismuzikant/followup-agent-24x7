"""Runs a product-supplied LangGraph graph behind the AgentRuntime port.

Graph contract:
- Input is {"inbound": <text>, "outbox": []}.
- Nodes read `GraphContext` through `runtime.context` (agent config, business, transcript,
  and the language model) and write this turn's messages to `outbox` as
  {"text": str, "payload": dict | None}.
- Every other state key is the conversation state, persisted by the checkpointer and
  exposed as the state snapshot.

Tracing (LangSmith) is optional and observability only: with `tracing=None` the turn runs
with tracing forced off, whatever the environment says.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph
from langsmith import Client, traceable, tracing_context

from ..domain.llm import Extraction, ExtractionRequest, LanguageModel, Reply, ReplyRequest
from ..domain.runtime import AgentTurn, OutboundMessage, TurnInput, TurnMetrics
from ..domain.thread import Thread, ThreadKey

TRANSIENT_KEYS = frozenset({"inbound", "outbox"})


@dataclass(frozen=True, slots=True)
class TurnTracing:
    """How turns are traced. The runtime adds the per-turn tags and metadata."""

    client: Client
    project_name: str
    run_name: str
    tags: Sequence[str] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GraphContext:
    turn: TurnInput
    llm: LanguageModel


def _without_self(inputs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in inputs.items() if key != "self"}


class MeteredLanguageModel:
    """Adds each call's token usage to the turn's metrics.

    Each call is also a child run ("llm.extract", "llm.compose_reply") when the turn is
    traced; otherwise `traceable` does nothing.
    """

    def __init__(self, inner: LanguageModel, metrics: TurnMetrics) -> None:
        self._inner = inner
        self._metrics = metrics

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    @property
    def prompt_versions(self) -> Mapping[str, str]:
        return self._inner.prompt_versions

    @traceable(name="llm.extract", run_type="chain", process_inputs=_without_self)
    def extract(self, request: ExtractionRequest) -> Extraction:
        result = self._inner.extract(request)
        self._metrics.usage = self._metrics.usage + result.usage
        return result

    @traceable(name="llm.compose_reply", run_type="chain", process_inputs=_without_self)
    def compose_reply(self, request: ReplyRequest) -> Reply:
        result = self._inner.compose_reply(request)
        self._metrics.usage = self._metrics.usage + result.usage
        return result


def _config(key: ThreadKey) -> RunnableConfig:
    return {"configurable": {"thread_id": str(key)}}


def _snapshot(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key not in TRANSIENT_KEYS}


class LangGraphRuntime:
    def __init__(
        self,
        graph: StateGraph[Any, Any, Any, Any],
        checkpointer: BaseCheckpointSaver[Any],
        llm: LanguageModel,
        tracing: TurnTracing | None = None,
    ) -> None:
        self._graph = graph.compile(checkpointer=checkpointer)
        self._llm = llm
        self._tracing = tracing

    def _traced_config(
        self, thread: Thread, turn: TurnInput, metrics: TurnMetrics
    ) -> tuple[RunnableConfig, UUID | None]:
        config = _config(thread.key)
        tracing = self._tracing
        if tracing is None:
            return config, None
        run_id = uuid4()
        config["run_id"] = run_id
        config["run_name"] = tracing.run_name
        config["tags"] = [*tracing.tags, thread.channel.value]
        config["metadata"] = {
            **tracing.metadata,
            "tenant_id": str(thread.tenant_id),
            "thread_key": str(thread.key),
            "channel": thread.channel.value,
            "agent_config_version": thread.agent_config_version,
            "prompt_versions": dict(metrics.prompt_versions),
        }
        return config, run_id

    def handle(self, thread: Thread, turn: TurnInput) -> AgentTurn:
        metrics = TurnMetrics(
            model=self._llm.model_name, prompt_versions=dict(self._llm.prompt_versions)
        )
        context = GraphContext(turn=turn, llm=MeteredLanguageModel(self._llm, metrics))
        config, run_id = self._traced_config(thread, turn, metrics)
        tracing = self._tracing
        # tracing_context pins the client (with its anonymizer) and project, and turns
        # tracing off entirely when it is not configured.
        with tracing_context(
            enabled=tracing is not None,
            client=tracing.client if tracing else None,
            project_name=tracing.project_name if tracing else None,
        ):
            # durability="exit": the checkpoint is written once, when the turn completes,
            # so a failure in a later node never leaves a half-done state behind.
            result = self._graph.invoke(
                {"inbound": turn.text, "outbox": []},
                config,
                context=context,
                durability="exit",
            )
        outbound = [
            OutboundMessage(text=item["text"], payload=item.get("payload"))
            for item in result.get("outbox", [])
        ]
        return AgentTurn(
            outbound=outbound, state=_snapshot(result), metrics=metrics, trace_run_id=run_id
        )

    def state(self, key: ThreadKey) -> Mapping[str, Any]:
        with tracing_context(enabled=False):
            return _snapshot(self._graph.get_state(_config(key)).values)
