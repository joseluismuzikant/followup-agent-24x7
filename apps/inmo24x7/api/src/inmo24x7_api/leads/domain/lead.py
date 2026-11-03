"""A lead: one per conversation thread, with the S5 statuses and their allowed transitions."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from followup_core.conversation.domain.answers import normalize

from .errors import InvalidLeadTransitionError, VisitCancelledError


class LeadStatus(StrEnum):
    QUALIFYING = "qualifying"  # Calificando
    VISIT_PROPOSED = "visit_proposed"  # Visita propuesta
    HUMAN_REQUESTED = "human_requested"  # Pidió hablar con alguien
    VISIT_CONFIRMED = "visit_confirmed"  # Visita confirmada (set by the team, Day 6)


# No new visit is proposed after a hand-off, so nothing goes back to visit_proposed. A
# cancelled visit (by the team) leaves the lead in human_requested, for the team to follow up.
ALLOWED_TRANSITIONS: Mapping[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.QUALIFYING: frozenset({LeadStatus.VISIT_PROPOSED, LeadStatus.HUMAN_REQUESTED}),
    LeadStatus.VISIT_PROPOSED: frozenset({LeadStatus.HUMAN_REQUESTED, LeadStatus.VISIT_CONFIRMED}),
    LeadStatus.HUMAN_REQUESTED: frozenset({LeadStatus.VISIT_CONFIRMED}),
    LeadStatus.VISIT_CONFIRMED: frozenset({LeadStatus.HUMAN_REQUESTED}),
}

# The statuses that wait for the team (the "Para atender" tab), until someone replies.
WAITING_FOR_TEAM = frozenset({LeadStatus.VISIT_PROPOSED, LeadStatus.HUMAN_REQUESTED})


class HandOffReason(StrEnum):
    HUMAN = "human"  # the lead asked for a person
    VISIT = "visit"  # picked a visit slot and left contact details
    QUALIFIED = "qualified"  # answered everything without picking a visit


@dataclass(frozen=True, slots=True)
class StatusChange:
    status: LeadStatus
    changed_at: datetime


@dataclass(frozen=True, slots=True)
class Lead:
    id: UUID
    tenant_id: UUID
    thread_id: UUID
    thread_key: str
    channel: str
    is_test: bool
    visitor_name: str | None
    contact: str | None
    answers: Mapping[str, Any]
    status: LeadStatus
    history: tuple[StatusChange, ...]
    handed_off_at: datetime | None
    hand_off_reason: HandOffReason | None
    created_at: datetime
    last_activity_at: datetime
    # The last message someone from the team sent the lead.
    last_human_reply_at: datetime | None = None

    @classmethod
    def start(
        cls,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        thread_key: str,
        channel: str,
        is_test: bool,
        now: datetime,
    ) -> "Lead":
        return cls(
            id=uuid4(),
            tenant_id=tenant_id,
            thread_id=thread_id,
            thread_key=thread_key,
            channel=channel,
            is_test=is_test,
            visitor_name=None,
            contact=None,
            answers={},
            status=LeadStatus.QUALIFYING,
            history=(StatusChange(LeadStatus.QUALIFYING, now),),
            handed_off_at=None,
            hand_off_reason=None,
            created_at=now,
            last_activity_at=now,
        )

    @property
    def is_handed_off(self) -> bool:
        return self.handed_off_at is not None

    @property
    def needs_attention(self) -> bool:
        """Waiting for the team: a proposed visit or a request to talk to someone, with no
        team reply since the hand-off. A confirmed visit never needs attention. The
        repository mirrors this rule in SQL (`attention_condition`)."""
        if self.status not in WAITING_FOR_TEAM:
            return False
        if self.last_human_reply_at is None:
            return True
        return self.handed_off_at is not None and self.last_human_reply_at < self.handed_off_at

    @property
    def search_text(self) -> str:
        """What the inbox search matches: name, contact (also as bare digits) and answers,
        lowercase and without accents."""
        words = [self.visitor_name or "", self.contact or "", digits(self.contact or "")]
        words += [str(value) for value in self.answers.values() if isinstance(value, str | int)]
        return normalize(" ".join(word for word in words if word))[:2000]

    def replied_by_team(self, at: datetime) -> "Lead":
        return replace(
            self, last_human_reply_at=at, last_activity_at=max(at, self.last_activity_at)
        )

    def touched(self, at: datetime) -> "Lead":
        return replace(self, last_activity_at=max(at, self.last_activity_at))

    def move_to(self, status: LeadStatus, at: datetime) -> "Lead":
        if status is self.status:
            return self
        if status not in ALLOWED_TRANSITIONS[self.status]:
            raise InvalidLeadTransitionError(f"{self.status} -> {status}")
        return replace(self, status=status, history=(*self.history, StatusChange(status, at)))

    def hand_off(self, reason: HandOffReason, at: datetime) -> "Lead":
        """Once per lead; a person asking for help also moves the status."""
        lead = self
        if reason is HandOffReason.HUMAN:
            lead = lead.move_to(LeadStatus.HUMAN_REQUESTED, at)
        if lead.is_handed_off:
            return lead
        return replace(lead, handed_off_at=at, hand_off_reason=reason)

    def with_details(
        self,
        *,
        answers: Mapping[str, Any],
        visitor_name: str | None,
        contact: str | None,
        at: datetime,
    ) -> "Lead":
        return replace(
            self,
            answers=dict(answers),
            visitor_name=visitor_name or self.visitor_name,
            contact=contact or self.contact,
            last_activity_at=max(at, self.last_activity_at),
        )


def digits(text: str) -> str:
    return "".join(char for char in text if char.isdigit())


class VisitStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Visit:
    id: UUID
    lead_id: UUID
    property_id: UUID | None  # None for a sample listing
    property_label: str
    starts_at: datetime
    status: VisitStatus
    created_at: datetime

    def confirm(self, starts_at: datetime | None = None) -> "Visit":
        """Confirmed by the team, optionally at another time. Confirming twice is a no-op."""
        if self.status is VisitStatus.CANCELLED:
            raise VisitCancelledError(str(self.id))
        return replace(self, status=VisitStatus.CONFIRMED, starts_at=starts_at or self.starts_at)

    def cancel(self) -> "Visit":
        return replace(self, status=VisitStatus.CANCELLED)
