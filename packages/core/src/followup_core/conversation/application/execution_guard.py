"""Per-turn execution limits: model calls, tokens and time.

Two kinds of state are kept apart on purpose:

- **per-turn execution state** (`TurnExecution`): created by the runtime for each turn,
  passed to the graph through `GraphContext.execution`, never checkpointed and never part
  of the conversation state;
- **persistent conversation state**: the graph's own state, checkpointed as before.

The only enforcement point is `MeteredLanguageModel`, which calls `before_model_call` and
`after_model_call` around every model call: nodes never count anything themselves. When a
limit is hit, the turn is stopped: no further model call is made (`ExecutionStopped`) and
the product's graph words what is left of the turn with its fixed texts.

Limits are code constants. Settings can only lower them (`ExecutionLimits.lowered`), and no
value can exceed its hard cap. No prompt ever contains a limit, and nothing a model returns
changes one.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from ..domain.llm import TokenUsage

Clock = Callable[[], float]


class TerminationReason(StrEnum):
    COMPLETED = "completed"
    MAX_MODEL_CALLS = "max_model_calls"
    TURN_DEADLINE = "turn_deadline"
    TOKEN_BUDGET = "token_budget"
    RECURSION_LIMIT = "recursion_limit"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    GUARD_BLOCKED = "guard_blocked"
    CONVERSATION_STALLED = "conversation_stalled"
    CONVERSATION_LIMIT = "conversation_limit"
    AGENT_FAILURE = "agent_failure"


# Which kind of call a model call is, for its own output cap.
EXTRACT_CALL = "extract"
REPLY_CALL = "reply"
ANSWER_CALL = "answer"

DEFAULT_MAX_MODEL_CALLS = 6
HARD_MAX_MODEL_CALLS = 8
DEFAULT_TURN_DEADLINE_SECONDS = 25.0
HARD_TURN_DEADLINE_SECONDS = 40.0
DEFAULT_MAX_TOKENS = 10_000
HARD_MAX_TOKENS = 16_000
DEFAULT_MAX_OUTPUT_TOKENS: Mapping[str, int] = MappingProxyType(
    {EXTRACT_CALL: 300, REPLY_CALL: 250, ANSWER_CALL: 300}
)
# When a provider reports no usage: about three characters per token.
CHARS_PER_TOKEN = 3


class ExecutionStopped(Exception):
    """No further model call in this turn."""

    def __init__(self, reason: TerminationReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    max_model_calls_per_turn: int = DEFAULT_MAX_MODEL_CALLS
    turn_deadline_seconds: float = DEFAULT_TURN_DEADLINE_SECONDS
    max_tokens_per_turn: int = DEFAULT_MAX_TOKENS
    max_output_tokens: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_MAX_OUTPUT_TOKENS)
    )

    def __post_init__(self) -> None:
        for name, value, cap in (
            ("max_model_calls_per_turn", self.max_model_calls_per_turn, HARD_MAX_MODEL_CALLS),
            ("turn_deadline_seconds", self.turn_deadline_seconds, HARD_TURN_DEADLINE_SECONDS),
            ("max_tokens_per_turn", self.max_tokens_per_turn, HARD_MAX_TOKENS),
        ):
            if not 0 < value <= cap:
                raise ValueError(f"{name} must be greater than 0 and at most {cap}.")
        for kind, value in self.max_output_tokens.items():
            if not 0 < value <= self.max_tokens_per_turn:
                raise ValueError(f"max_output_tokens[{kind}] is out of range.")
        object.__setattr__(
            self, "max_output_tokens", MappingProxyType(dict(self.max_output_tokens))
        )

    def lowered(
        self,
        *,
        max_model_calls_per_turn: int | None = None,
        turn_deadline_seconds: float | None = None,
        max_tokens_per_turn: int | None = None,
    ) -> "ExecutionLimits":
        """Settings overrides: each one can only lower its limit; a higher value is ignored."""

        def low(current: float, wanted: float | None) -> float:
            return current if wanted is None or wanted <= 0 else min(current, wanted)

        return ExecutionLimits(
            max_model_calls_per_turn=int(
                low(self.max_model_calls_per_turn, max_model_calls_per_turn)
            ),
            turn_deadline_seconds=low(self.turn_deadline_seconds, turn_deadline_seconds),
            max_tokens_per_turn=int(low(self.max_tokens_per_turn, max_tokens_per_turn)),
            max_output_tokens=self.max_output_tokens,
        )

    def output_tokens(self, kind: str) -> int:
        return self.max_output_tokens.get(kind, DEFAULT_MAX_OUTPUT_TOKENS[REPLY_CALL])


def estimate_tokens(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN)


@dataclass(slots=True)
class TurnExecution:
    """What this turn has spent so far. Mutable, per turn, never persisted."""

    limits: ExecutionLimits
    started: float
    # The inbound job's last attempt: a provider failure runs degraded instead of raising.
    final_attempt: bool = False
    model_calls: int = 0
    tokens: int = 0
    stage: str = "start"
    stopped: TerminationReason | None = None
    # Set by the product's graph when it ended the turn for its own reasons (a stalled
    # conversation, a blocked reply): logged like a stop, without stopping model calls.
    outcome: TerminationReason | None = None
    guard_blocks: int = 0

    @property
    def is_stopped(self) -> bool:
        return self.stopped is not None

    def stop(self, reason: TerminationReason) -> None:
        if self.stopped is None:
            self.stopped = reason

    def finish(self, reason: TerminationReason) -> None:
        """The graph's own outcome (it does not stop model calls)."""
        if self.outcome is None:
            self.outcome = reason

    @property
    def termination_reason(self) -> TerminationReason:
        return self.stopped or self.outcome or TerminationReason.COMPLETED


class ExecutionGuard:
    """Checks a turn's limits around every model call."""

    def __init__(self, execution: TurnExecution, clock: Clock = time.monotonic) -> None:
        self.execution = execution
        self._clock = clock

    @classmethod
    def start(
        cls,
        limits: ExecutionLimits,
        clock: Clock = time.monotonic,
        *,
        final_attempt: bool = False,
    ) -> "ExecutionGuard":
        return cls(TurnExecution(limits, clock(), final_attempt=final_attempt), clock)

    def elapsed_seconds(self) -> float:
        return self._clock() - self.execution.started

    def before_model_call(self, kind: str, estimated_input_tokens: int) -> int:
        """Raises ExecutionStopped when this call would break a limit; otherwise returns the
        call's output cap (the provider's max_tokens)."""
        execution = self.execution
        limits = execution.limits
        if execution.stopped is not None:
            raise ExecutionStopped(execution.stopped)
        output_cap = limits.output_tokens(kind)
        if execution.model_calls >= limits.max_model_calls_per_turn:
            reason = TerminationReason.MAX_MODEL_CALLS
        elif self.elapsed_seconds() >= limits.turn_deadline_seconds:
            reason = TerminationReason.TURN_DEADLINE
        elif execution.tokens + estimated_input_tokens + output_cap > limits.max_tokens_per_turn:
            reason = TerminationReason.TOKEN_BUDGET
        else:
            execution.model_calls += 1
            return output_cap
        execution.stop(reason)
        raise ExecutionStopped(reason)

    def after_model_call(
        self, usage: TokenUsage, estimated_input_tokens: int, output_text: str = ""
    ) -> None:
        """Adds what the call spent (estimated when the provider reports nothing). A call
        that ends past the deadline or the budget stops the turn: no further call."""
        execution = self.execution
        if usage.reported:
            spent = usage.input_tokens + usage.output_tokens
        else:
            spent = estimated_input_tokens + estimate_tokens(output_text)
        execution.tokens += spent
        if execution.tokens > execution.limits.max_tokens_per_turn:
            execution.stop(TerminationReason.TOKEN_BUDGET)
        elif self.elapsed_seconds() >= execution.limits.turn_deadline_seconds:
            execution.stop(TerminationReason.TURN_DEADLINE)
