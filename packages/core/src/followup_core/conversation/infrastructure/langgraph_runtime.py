"""Runs a product-supplied LangGraph graph behind the AgentRuntime port.

Graph contract:
- Input is {"inbound": <text>, "outbox": [], "opt_out": False}.
- Nodes read `GraphContext` through `runtime.context` (agent config, business, transcript,
  the language model and the product's tools) and write this turn's messages to `outbox` as
  {"text": str, "payload": dict | None, "author": "agent" | "system" (optional)}.
- A node may set `opt_out` to True: the message asked not to be written to again ("BAJA").
- Every other state key is the conversation state, persisted by the checkpointer and
  exposed as the state snapshot.

Tracing (LangSmith) is optional and observability only: with `tracing=None` the turn runs
with tracing forced off, whatever the environment says. With a `usage` recorder, every model
call of the turn is recorded (tokens, latency, success) as it happens.

Execution limits (application/execution_guard.py): every turn gets its own `TurnExecution`
(`GraphContext.execution`, never checkpointed) and every model call goes through the guard.
`recursion_limit` is set too, as a backstop. A turn that did not simply complete is logged as
`agent_terminated` (codes and counts, never text), and its reason is the transient
`termination_reason` key of the result (shown in the trace's outputs).
"""

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID, uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import StateGraph
from langsmith import Client, traceable, tracing_context
from langsmith.address import AgentAddress

from ..application.execution_guard import (
    ANSWER_CALL,
    EXTRACT_CALL,
    REPLY_CALL,
    Clock,
    ExecutionGuard,
    ExecutionLimits,
    ExecutionStopped,
    TerminationReason,
    TurnExecution,
    estimate_tokens,
)
from ..domain.llm import (
    Extraction,
    ExtractionRequest,
    LanguageModel,
    Reply,
    ReplyIntent,
    ReplyRequest,
    TokenUsage,
)
from ..domain.runtime import AgentTurn, OutboundMessage, TurnInput, TurnMetrics
from ..domain.thread import Author, Channel, Thread, ThreadKey
from ..domain.tools import Tool, ToolRegistry
from ..domain.usage import LlmCall, LlmOperation, LlmUsageRecorder

logger = logging.getLogger("followup.agent")

TRANSIENT_KEYS = frozenset({"inbound", "outbox", "opt_out", "termination_reason"})

_Result = TypeVar("_Result", Extraction, Reply)


@dataclass(frozen=True, slots=True)
class TurnTracing:
    """How turns are traced. The runtime adds the per-turn tags and metadata."""

    client: Client
    # Where runs go: a LangSmith agent address, or a tracing project when there is none.
    project_name: str | None
    run_name: str
    tags: Sequence[str] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    address: AgentAddress | None = None


def _new_execution() -> TurnExecution:
    return TurnExecution(ExecutionLimits(), time.monotonic())


@dataclass(frozen=True, slots=True)
class GraphContext:
    turn: TurnInput
    llm: LanguageModel
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    # This turn's execution state (limits, counts, why it stopped). Per turn, never
    # checkpointed; the graph reads it, only the guard in `llm` changes the counts.
    execution: TurnExecution = field(default_factory=_new_execution)


def _traced_tool(tool: Tool) -> Any:
    """Each tool call is a child run of the turn named after the tool (no-op untraced)."""
    return traceable(name=tool.name, run_type="tool")(tool.handler)


def _without_self(inputs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in inputs.items() if key != "self"}


class MeteredLanguageModel:
    """Adds each call's token usage to the turn's metrics, and records every call (failed
    ones too) with the usage recorder when there is one.

    Each call is also a child run ("llm.extract", "llm.compose_reply") when the turn is
    traced; otherwise `traceable` does nothing.
    """

    def __init__(
        self,
        inner: LanguageModel,
        metrics: TurnMetrics,
        thread: Thread | None = None,
        usage: LlmUsageRecorder | None = None,
        guard: ExecutionGuard | None = None,
    ) -> None:
        self._inner = inner
        self._metrics = metrics
        self._thread = thread
        self._usage = usage
        self._guard = guard

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    @property
    def prompt_versions(self) -> Mapping[str, str]:
        return self._inner.prompt_versions

    def _estimate(self, request: ExtractionRequest | ReplyRequest) -> int:
        estimate: Callable[[Any], int] | None = getattr(self._inner, "estimate_input_tokens", None)
        if callable(estimate):
            return int(estimate(request))
        return estimate_tokens(repr(request))

    def _metered(
        self,
        operation: LlmOperation,
        kind: str,
        request: ExtractionRequest | ReplyRequest,
        call: Callable[[Any], _Result],
    ) -> _Result:
        """The guard first (it raises ExecutionStopped and nothing is called), then the
        call with the guard's output cap, then what it spent."""
        estimated = self._estimate(request)
        guard = self._guard
        if guard is not None:
            cap = guard.before_model_call(kind, estimated)
            request = replace(request, max_output_tokens=cap)
        started = time.perf_counter()
        try:
            result = call(request)
        except Exception:
            self._record(operation, TokenUsage(), started, succeeded=False)
            if guard is not None:
                guard.after_model_call(TokenUsage(), estimated)
            raise
        self._metrics.usage = self._metrics.usage + result.usage
        self._record(operation, result.usage, started, succeeded=True)
        if guard is not None:
            text = result.text if isinstance(result, Reply) else ""
            guard.after_model_call(result.usage, estimated, text)
        return result

    def _record(
        self, operation: LlmOperation, usage: TokenUsage, started: float, *, succeeded: bool
    ) -> None:
        thread = self._thread
        if self._usage is None or thread is None:
            return
        self._usage.record(
            LlmCall(
                tenant_id=thread.tenant_id,
                thread_id=thread.id,
                channel=thread.channel.value,
                is_test=thread.channel is Channel.SIMULATOR,
                operation=operation,
                model=self._inner.model_name,
                usage=usage,
                latency_ms=round((time.perf_counter() - started) * 1000),
                succeeded=succeeded,
                created_at=datetime.now(UTC),
            )
        )

    @traceable(name="llm.extract", run_type="chain", process_inputs=_without_self)
    def extract(self, request: ExtractionRequest) -> Extraction:
        return self._metered(LlmOperation.EXTRACT, EXTRACT_CALL, request, self._inner.extract)

    @traceable(name="llm.compose_reply", run_type="chain", process_inputs=_without_self)
    def compose_reply(self, request: ReplyRequest) -> Reply:
        kind = ANSWER_CALL if request.intent is ReplyIntent.ANSWER_QUESTION else REPLY_CALL
        return self._metered(LlmOperation.COMPOSE_REPLY, kind, request, self._inner.compose_reply)


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
        tools: ToolRegistry | None = None,
        usage: LlmUsageRecorder | None = None,
        limits: ExecutionLimits | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        # One superstep per node plus two: a linear graph never reaches it; a loop does.
        self.recursion_limit = len(graph.nodes) + 2
        self._graph = graph.compile(checkpointer=checkpointer)
        self._limits = limits or ExecutionLimits()
        self._clock = clock
        self._llm = llm
        self._tracing = tracing
        self._usage = usage
        self._tools = (tools or ToolRegistry()).wrapped(_traced_tool)

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
        guard = ExecutionGuard.start(self._limits, self._clock, final_attempt=turn.final_attempt)
        context = GraphContext(
            turn=turn,
            llm=MeteredLanguageModel(self._llm, metrics, thread, self._usage, guard),
            tools=self._tools,
            execution=guard.execution,
        )
        config, run_id = self._traced_config(thread, turn, metrics)
        config["recursion_limit"] = self.recursion_limit
        tracing = self._tracing
        # tracing_context pins the client (with its anonymizer) and the destination (agent
        # address or project, never both), and turns tracing off entirely when it is not
        # configured.
        with tracing_context(
            enabled=tracing is not None,
            client=tracing.client if tracing else None,
            address=tracing.address if tracing else None,
            project_name=tracing.project_name if tracing and not tracing.address else None,
        ):
            # durability="exit": the checkpoint is written once, when the turn completes,
            # so a failure in a later node never leaves a half-done state behind.
            try:
                result = self._graph.invoke(
                    {"inbound": turn.text, "outbox": [], "opt_out": False},
                    config,
                    context=context,
                    durability="exit",
                )
            except GraphRecursionError as error:
                # Nothing is kept: the caller writes only after a completed turn, and the
                # checkpoint is on its transaction, which rolls back with the error.
                guard.execution.stop(TerminationReason.RECURSION_LIMIT)
                self._finish(thread, guard, metrics)
                raise ExecutionStopped(TerminationReason.RECURSION_LIMIT) from error
        reason = self._finish(thread, guard, metrics)
        outbound = [
            OutboundMessage(
                text=item["text"],
                payload=item.get("payload"),
                author=Author(item.get("author") or Author.AGENT),
            )
            for item in result.get("outbox", [])
        ]
        return AgentTurn(
            outbound=outbound,
            state=_snapshot(result),
            metrics=metrics,
            trace_run_id=run_id,
            opt_out=bool(result.get("opt_out")),
            termination_reason=reason.value,
        )

    def _finish(
        self, thread: Thread, guard: ExecutionGuard, metrics: TurnMetrics
    ) -> TerminationReason:
        execution = guard.execution
        metrics.model_calls = execution.model_calls
        metrics.tokens = execution.tokens
        metrics.elapsed_ms = round(guard.elapsed_seconds() * 1000)
        reason = execution.termination_reason
        if reason is not TerminationReason.COMPLETED:
            logger.warning(
                "agent_terminated",
                extra={
                    "reason": reason.value,
                    "stage": execution.stage,
                    "model_calls": execution.model_calls,
                    "tokens": execution.tokens,
                    "elapsed_ms": metrics.elapsed_ms,
                    "tenant_id": str(thread.tenant_id),
                    "thread_id": str(thread.id),
                },
            )
        return reason

    def state(self, key: ThreadKey) -> Mapping[str, Any]:
        with tracing_context(enabled=False):
            return _snapshot(self._graph.get_state(_config(key)).values)
