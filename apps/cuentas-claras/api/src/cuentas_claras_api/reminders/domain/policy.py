"""A business's reminder policy (C4): the ordered steps around the due date, the send
window, holidays and the pause while a client promised to pay.

Steps are relative to an invoice's due date ("3 days before", "the due date", "7 days
after"). The last one escalates: it sends nothing to the client, stops the reminders for
that invoice and emails the owner. A step keeps its id when edited, so what was already
sent for an invoice stays counted when its offset changes.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, time
from enum import StrEnum
from uuid import UUID, uuid4, uuid5

MIN_OFFSET = -30
MAX_OFFSET = 90
MAX_STEPS = 8


class ReminderPolicyError(ValueError):
    """`field` says what is wrong (the API returns it)."""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


class StepKind(StrEnum):
    REMINDER = "reminder"  # a WhatsApp template to the client
    ESCALATE = "escalate"  # nothing to the client: stop and email the owner


class TemplateKind(StrEnum):
    """Which of the business's templates a reminder uses. Several invoices of one client
    due for a step the same day go out together with SEVERAL."""

    BEFORE = "before"
    DUE = "due"
    AFTER = "after"
    SEVERAL = "several"


STEP_TEMPLATES = (TemplateKind.BEFORE, TemplateKind.DUE, TemplateKind.AFTER)


def template_for_offset(offset_days: int) -> TemplateKind:
    if offset_days < 0:
        return TemplateKind.BEFORE
    if offset_days == 0:
        return TemplateKind.DUE
    return TemplateKind.AFTER


class WindowPreset(StrEnum):
    TEAM = "team"  # Horario del equipo (Configuración), weekdays only
    MORNINGS = "mornings"  # Mañanas 9–12
    BUSINESS_DAY = "business_day"  # Todo el día hábil 9–18
    CUSTOM = "custom"


PRESET_HOURS = {
    WindowPreset.MORNINGS: (time(9), time(12)),
    WindowPreset.BUSINESS_DAY: (time(9), time(18)),
}


@dataclass(frozen=True, slots=True)
class SendWindow:
    """When reminders may go out, in the business's timezone; never on weekends. TEAM
    follows the team's hours of each weekday; the others are one range for every
    weekday."""

    preset: WindowPreset = WindowPreset.MORNINGS
    # Only for CUSTOM.
    start: time | None = None
    end: time | None = None

    def __post_init__(self) -> None:
        if self.preset is WindowPreset.CUSTOM:
            if self.start is None or self.end is None:
                raise ReminderPolicyError("window")
            if not (time(6) <= self.start < self.end <= time(22)):
                raise ReminderPolicyError("window")
            if self.start.second or self.end.second:
                raise ReminderPolicyError("window")
        elif self.start is not None or self.end is not None:
            object.__setattr__(self, "start", None)
            object.__setattr__(self, "end", None)

    def hours(self) -> tuple[time, time] | None:
        """The one range of a fixed or custom window (None for TEAM)."""
        if self.preset is WindowPreset.CUSTOM:
            assert self.start is not None and self.end is not None
            return self.start, self.end
        return PRESET_HOURS.get(self.preset)


DEFAULT_WINDOW = SendWindow()


@dataclass(frozen=True, slots=True)
class ReminderStep:
    offset_days: int
    kind: StepKind = StepKind.REMINDER
    active: bool = True
    template_kind: TemplateKind | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.kind is StepKind.REMINDER:
            kind = self.template_kind or template_for_offset(self.offset_days)
            if kind is TemplateKind.SEVERAL:
                raise ReminderPolicyError("steps")
            object.__setattr__(self, "template_kind", kind)
        else:
            object.__setattr__(self, "template_kind", None)

    @property
    def escalates(self) -> bool:
        return self.kind is StepKind.ESCALATE


def validate_steps(steps: Sequence[ReminderStep]) -> tuple[ReminderStep, ...]:
    """Ordered by offset; offsets unique and between -30 and +90; at most one escalation
    and, if there is one, it is the last step."""
    if not 1 <= len(steps) <= MAX_STEPS:
        raise ReminderPolicyError("steps")
    ordered = tuple(sorted(steps, key=lambda step: step.offset_days))
    offsets = [step.offset_days for step in ordered]
    if len(set(offsets)) != len(offsets):
        raise ReminderPolicyError("offset_duplicate")
    if any(not MIN_OFFSET <= offset <= MAX_OFFSET for offset in offsets):
        raise ReminderPolicyError("offset_range")
    if len({step.id for step in ordered}) != len(ordered):
        raise ReminderPolicyError("steps")
    escalations = [index for index, step in enumerate(ordered) if step.escalates]
    if len(escalations) > 1 or (escalations and escalations[0] != len(ordered) - 1):
        raise ReminderPolicyError("escalation_last")
    return ordered


# The default steps' ids are derived from the business and the step, so a business that
# never saved its policy still has stable ids (what was sent stays counted).
_DEFAULT_IDS = UUID("6f0c5a52-3c55-4c1e-9a43-0b6b2f0a9d11")


def default_steps(tenant_id: UUID) -> tuple[ReminderStep, ...]:
    def step(offset: int, kind: StepKind = StepKind.REMINDER) -> ReminderStep:
        return ReminderStep(offset, kind, id=uuid5(_DEFAULT_IDS, f"{tenant_id}:{offset}:{kind}"))

    return (step(-3), step(0), step(7), step(15, StepKind.ESCALATE))


@dataclass(frozen=True, slots=True)
class ReminderPolicy:
    tenant_id: UUID
    steps: tuple[ReminderStep, ...]
    window: SendWindow = DEFAULT_WINDOW
    skip_holidays: bool = True
    pause_on_promise: bool = True
    # When the owner first saved it (onboarding "Recordatorios" or C4): the checklist fact.
    configured_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", validate_steps(self.steps))

    @classmethod
    def default(cls, tenant_id: UUID) -> "ReminderPolicy":
        return cls(tenant_id, default_steps(tenant_id))

    @property
    def active_steps(self) -> tuple[ReminderStep, ...]:
        return tuple(step for step in self.steps if step.active)

    def step(self, step_id: UUID) -> ReminderStep | None:
        return next((step for step in self.steps if step.id == step_id), None)

    def with_changes(
        self,
        steps: Sequence[ReminderStep],
        window: SendWindow,
        skip_holidays: bool,
        pause_on_promise: bool,
        now: datetime,
    ) -> "ReminderPolicy":
        return replace(
            self,
            steps=tuple(steps),
            window=window,
            skip_holidays=skip_holidays,
            pause_on_promise=pause_on_promise,
            configured_at=self.configured_at or now,
            updated_at=now,
        )
