"""A lead: one per conversation thread, with the S5 statuses and their allowed transitions."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from .errors import InvalidLeadTransitionError


class LeadStatus(StrEnum):
    QUALIFYING = "qualifying"  # Calificando
    VISIT_PROPOSED = "visit_proposed"  # Visita propuesta
    HUMAN_REQUESTED = "human_requested"  # Pidió hablar con alguien
    VISIT_CONFIRMED = "visit_confirmed"  # Visita confirmada (set by the team, Day 6)


# No new visit is proposed after a hand-off, so nothing goes back to visit_proposed.
ALLOWED_TRANSITIONS: Mapping[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.QUALIFYING: frozenset({LeadStatus.VISIT_PROPOSED, LeadStatus.HUMAN_REQUESTED}),
    LeadStatus.VISIT_PROPOSED: frozenset({LeadStatus.HUMAN_REQUESTED, LeadStatus.VISIT_CONFIRMED}),
    LeadStatus.HUMAN_REQUESTED: frozenset({LeadStatus.VISIT_CONFIRMED}),
    LeadStatus.VISIT_CONFIRMED: frozenset(),
}


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
