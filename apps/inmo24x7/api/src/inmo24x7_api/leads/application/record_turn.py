"""Keeps the lead of a thread in step with the agent's graph state after every turn."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from followup_core.conversation.application.threads import HandledTurn
from followup_core.conversation.domain.thread import Channel

from ..domain.lead import HandOffReason, Lead, LeadStatus, Visit, VisitStatus
from ..domain.repositories import LeadRepository


def own_property_id(value: Any) -> UUID | None:
    """Own properties have UUID ids; sample listings have slugs and are not stored."""
    try:
        return UUID(str(value))
    except ValueError:
        return None


class RecordLeadTurn:
    """A `TurnObserver`: runs in the turn's transaction, so a failure rolls the turn back.

    It projects the state onto the lead (idempotent): answers, name and contact, the visit
    the lead picked, the hand-off, and the own properties the agent showed.
    """

    def __init__(self, leads: LeadRepository) -> None:
        self._leads = leads

    def on_turn(self, turn: HandledTurn) -> None:
        thread = turn.thread
        at = turn.inbound.created_at
        lead = self._leads.get_by_thread(thread.id) or Lead.start(
            tenant_id=thread.tenant_id,
            thread_id=thread.id,
            thread_key=str(thread.key),
            channel=thread.channel.value,
            is_test=thread.channel is Channel.SIMULATOR,
            now=at,
        )
        state = turn.state
        lead = lead.with_details(
            answers=state.get("answers") or {},
            visitor_name=state.get("visitor_name"),
            contact=state.get("contact"),
            at=at,
        )

        visit = state.get("visit")
        if visit:
            lead = lead.move_to(LeadStatus.VISIT_PROPOSED, at) if not lead.is_handed_off else lead
        reason = state.get("hand_off_reason")
        if reason:
            lead = lead.hand_off(HandOffReason(reason), at)
        self._leads.save(lead)

        if visit and not self._leads.visits(lead.id):
            self._leads.add_visit(_visit(lead.id, visit, at))
        shown = [own_property_id(item) for item in state.get("shown_property_ids") or []]
        self._leads.record_matches(lead.id, [item for item in shown if item], at)


def _visit(lead_id: UUID, visit: Mapping[str, Any], at: datetime) -> Visit:
    return Visit(
        id=uuid4(),
        lead_id=lead_id,
        property_id=own_property_id(visit["property_id"]),
        property_label=str(visit["property_label"])[:320],
        starts_at=datetime.fromisoformat(visit["starts_at"]),
        status=VisitStatus.PROPOSED,
        created_at=at,
    )
