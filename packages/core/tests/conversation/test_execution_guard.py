"""Per-turn execution limits (conversation/application/execution_guard.py), with a fake
clock: no real sleeps."""

import pytest
from followup_core.conversation.application.execution_guard import (
    ExecutionGuard,
    ExecutionLimits,
    ExecutionStopped,
    TerminationReason,
)
from followup_core.conversation.domain.llm import TokenUsage


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_defaults_and_hard_caps() -> None:
    limits = ExecutionLimits()

    assert (limits.max_model_calls_per_turn, limits.turn_deadline_seconds) == (6, 25.0)
    assert limits.max_tokens_per_turn == 10_000
    assert dict(limits.max_output_tokens) == {"extract": 300, "reply": 250, "answer": 300}
    with pytest.raises(ValueError):
        ExecutionLimits(max_model_calls_per_turn=9)
    with pytest.raises(ValueError):
        ExecutionLimits(turn_deadline_seconds=41)
    with pytest.raises(ValueError):
        ExecutionLimits(max_tokens_per_turn=16_001)


def test_settings_can_only_lower_a_limit() -> None:
    lowered = ExecutionLimits().lowered(
        max_model_calls_per_turn=4, turn_deadline_seconds=99, max_tokens_per_turn=None
    )

    assert lowered.max_model_calls_per_turn == 4
    assert lowered.turn_deadline_seconds == 25.0  # 99 would raise it: ignored
    assert lowered.max_tokens_per_turn == 10_000


def test_model_calls_stop_at_the_limit_and_stay_stopped() -> None:
    guard = ExecutionGuard.start(ExecutionLimits(max_model_calls_per_turn=2), FakeClock())

    assert guard.before_model_call("extract", 10) == 300
    assert guard.before_model_call("reply", 10) == 250
    with pytest.raises(ExecutionStopped) as stopped:
        guard.before_model_call("reply", 10)
    assert stopped.value.reason is TerminationReason.MAX_MODEL_CALLS
    with pytest.raises(ExecutionStopped):
        guard.before_model_call("reply", 1)
    assert guard.execution.model_calls == 2


def test_the_deadline_is_checked_before_every_call_and_after_a_slow_one() -> None:
    clock = FakeClock()
    guard = ExecutionGuard.start(ExecutionLimits(turn_deadline_seconds=10), clock)

    guard.before_model_call("extract", 10)
    clock.now += 11  # a slow call
    guard.after_model_call(TokenUsage(10, 10, reported=True), 10)

    assert guard.execution.stopped is TerminationReason.TURN_DEADLINE
    with pytest.raises(ExecutionStopped):
        guard.before_model_call("reply", 10)


def test_the_token_budget_counts_reported_usage_or_estimates_it() -> None:
    guard = ExecutionGuard.start(ExecutionLimits(max_tokens_per_turn=1000), FakeClock())

    guard.before_model_call("extract", 300)
    guard.after_model_call(TokenUsage(), 300, "x" * 300)  # not reported: estimated
    assert guard.execution.tokens == 400

    # The next call would not fit its input plus its output cap.
    with pytest.raises(ExecutionStopped) as stopped:
        guard.before_model_call("reply", 400)
    assert stopped.value.reason is TerminationReason.TOKEN_BUDGET


def test_reported_usage_over_the_budget_stops_the_turn() -> None:
    guard = ExecutionGuard.start(ExecutionLimits(max_tokens_per_turn=1000), FakeClock())

    guard.before_model_call("extract", 10)
    guard.after_model_call(TokenUsage(900, 200, reported=True), 10)

    assert guard.execution.termination_reason is TerminationReason.TOKEN_BUDGET


def test_an_outcome_of_the_graph_does_not_stop_model_calls() -> None:
    guard = ExecutionGuard.start(ExecutionLimits(), FakeClock())

    guard.execution.finish(TerminationReason.CONVERSATION_STALLED)

    assert guard.before_model_call("reply", 10) == 250
    assert guard.execution.termination_reason is TerminationReason.CONVERSATION_STALLED
