"""Where a conversation stands commercially, whether a turn moved it forward, and what to do
when it stops moving.

Everything here is deterministic code over the graph state. No limit or counter is ever in
a prompt, and nothing a model returns changes one: the model's only influence is through
values the graph already validated (an answer, a pick).

Stall policy (constants, not settings):
- the same reply intent `REPEATED_INTENT_TURNS` turns in a row (AFTER_HAND_OFF aside) is
  stalled at once;
- `OFFER_HUMAN_AFTER` turns without progress, or `OFFER_HUMAN_DEFERRED` deferred answers,
  ask once whether a person should contact them (OFFER_HUMAN);
- `HAND_OFF_AFTER` turns without progress hand off as "stalled";
- `CONVERSATION_LIMIT_TURNS` turns hand off as "stalled" too (logged as conversation_limit).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from followup_core.conversation.domain.llm import ReplyIntent

REPEATED_INTENT_TURNS = 3
OFFER_HUMAN_AFTER = 5
OFFER_HUMAN_DEFERRED = 2
HAND_OFF_AFTER = 8
CONVERSATION_LIMIT_TURNS = 40
# After a hand-off, at most one fixed reply per thread in this window (the first one after
# the hand-off is worded by the model).
AFTER_HAND_OFF_QUIET_HOURS = 12


class Stage(StrEnum):
    NEW = "new"
    QUALIFYING = "qualifying"
    OPTIONS_SHOWN = "options_shown"
    PROPERTY_CHOSEN = "property_chosen"
    VISIT_OFFERED = "visit_offered"
    VISIT_NOTED = "visit_noted"
    CLOSED_NO_FIT = "closed_no_fit"
    HANDED_OFF = "handed_off"


# Forward order: a higher rank is progress. CLOSED_NO_FIT and HANDED_OFF end the flow.
STAGE_RANK: Mapping[Stage, int] = {
    Stage.NEW: 0,
    Stage.QUALIFYING: 1,
    Stage.OPTIONS_SHOWN: 2,
    Stage.PROPERTY_CHOSEN: 3,
    Stage.VISIT_OFFERED: 4,
    Stage.VISIT_NOTED: 5,
    Stage.CLOSED_NO_FIT: 5,
    Stage.HANDED_OFF: 6,
}


def commercial_stage(state: Mapping[str, Any]) -> Stage:
    """A pure function of existing state keys. QUALIFYING covers every turn before the
    options are shown (a required filter or an enabled question is still missing)."""
    if state.get("hand_off_reason"):
        return Stage.HANDED_OFF
    if state.get("last_intent") == ReplyIntent.NO_FIT.value:
        return Stage.CLOSED_NO_FIT
    if state.get("visit"):
        return Stage.VISIT_NOTED
    if state.get("visit_offer"):
        return Stage.VISIT_OFFERED
    if state.get("chosen_property_ids"):
        return Stage.PROPERTY_CHOSEN
    if state.get("properties_presented"):
        return Stage.OPTIONS_SHOWN
    if not state.get("turns"):
        return Stage.NEW
    return Stage.QUALIFYING


def goal_complete(state: Mapping[str, Any]) -> bool:
    """The flow's goal: a noted visit handed off, or a qualified or human hand-off."""
    reason = state.get("hand_off_reason")
    if not reason:
        return False
    return bool(state.get("visit")) or reason in ("qualified", "human", "visit")


def terminal(state: Mapping[str, Any]) -> bool:
    """Nothing commercial is planned any more: the goal is complete or nothing fits."""
    return goal_complete(state) or commercial_stage(state) is Stage.CLOSED_NO_FIT


@dataclass(frozen=True, slots=True)
class Progress:
    stage: str = Stage.NEW.value
    answered_keys_count: int = 0
    chosen_count: int = 0
    last_progress_turn: int = 0
    # The last reply intent and how many turns in a row it was the last one.
    last_intent: str | None = None
    same_intent_turns: int = 0

    @classmethod
    def of(cls, state: Mapping[str, Any]) -> "Progress":
        raw = state.get("progress")
        if not isinstance(raw, Mapping):
            # An old checkpoint: start counting from where the conversation is.
            return cls(
                stage=commercial_stage(state).value,
                answered_keys_count=len(state.get("answers") or {}),
                chosen_count=len(state.get("chosen_property_ids") or []),
                last_progress_turn=int(state.get("turns") or 0),
            )
        return cls(
            stage=str(raw.get("stage") or Stage.NEW.value),
            answered_keys_count=int(raw.get("answered_keys_count") or 0),
            chosen_count=int(raw.get("chosen_count") or 0),
            last_progress_turn=int(raw.get("last_progress_turn") or 0),
            last_intent=raw.get("last_intent"),
            same_intent_turns=int(raw.get("same_intent_turns") or 0),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "answered_keys_count": self.answered_keys_count,
            "chosen_count": self.chosen_count,
            "last_progress_turn": self.last_progress_turn,
            "last_intent": self.last_intent,
            "same_intent_turns": self.same_intent_turns,
        }


def turns_since_progress(state: Mapping[str, Any]) -> int:
    return int(state.get("turns") or 0) - Progress.of(state).last_progress_turn


def advance(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    refined: bool = False,
    answered: bool = False,
    sent_intent: str | None = None,
) -> Progress:
    """The progress after a turn: `after` is the state at the end of the turn, and
    `sent_intent` the intent of the last message the lead actually got (None: nothing was
    sent, the streak stays as it was)."""
    previous = Progress.of(before)
    stage = commercial_stage(after)
    answered_keys = len(after.get("answers") or {})
    chosen = len(after.get("chosen_property_ids") or [])
    moved = (
        STAGE_RANK[stage] > STAGE_RANK.get(Stage(previous.stage), 0)
        or answered_keys > previous.answered_keys_count
        or chosen > previous.chosen_count
        or refined
        or answered
    )
    turns = int(after.get("turns") or 0)
    intent = sent_intent or previous.last_intent
    if sent_intent is None:
        same = previous.same_intent_turns
    else:
        same = previous.same_intent_turns + 1 if sent_intent == previous.last_intent else 1
    return Progress(
        stage=stage.value,
        answered_keys_count=max(answered_keys, previous.answered_keys_count),
        chosen_count=max(chosen, previous.chosen_count),
        last_progress_turn=turns if moved else previous.last_progress_turn,
        last_intent=intent,
        same_intent_turns=same if not moved else 1,
    )


class StallAction(StrEnum):
    NONE = "none"
    OFFER_HUMAN = "offer_human"
    HAND_OFF = "hand_off"


@dataclass(frozen=True, slots=True)
class StallDecision:
    action: StallAction
    # Logged: "conversation_stalled" or "conversation_limit".
    reason: str | None = None


def stall_decision(
    state: Mapping[str, Any], *, progressing: bool, repeated: bool = False
) -> StallDecision:
    """For the turn being planned. `progressing`: this turn's own message already moves the
    conversation (a new answer, a pick, a changed search), so it is not a stalled turn.
    `repeated`: the planned turn would end on the same intent as the last
    REPEATED_INTENT_TURNS - 1 turns (AFTER_HAND_OFF aside): stalled at once."""
    if state.get("hand_off_reason"):
        return StallDecision(StallAction.NONE)
    turns = int(state.get("turns") or 0)
    if turns + 1 >= CONVERSATION_LIMIT_TURNS:
        return StallDecision(StallAction.HAND_OFF, "conversation_limit")
    if progressing:
        return StallDecision(StallAction.NONE)
    progress = Progress.of(state)
    # This turn counts as one more without progress.
    since = turns + 1 - progress.last_progress_turn
    if since >= HAND_OFF_AFTER or (repeated and state.get("stall_offered")):
        return StallDecision(StallAction.HAND_OFF, "conversation_stalled")
    deferred = int(state.get("answers_deferred") or 0) >= OFFER_HUMAN_DEFERRED
    if (since >= OFFER_HUMAN_AFTER or deferred or repeated) and not state.get("stall_offered"):
        return StallDecision(StallAction.OFFER_HUMAN, "conversation_stalled")
    return StallDecision(StallAction.NONE)
