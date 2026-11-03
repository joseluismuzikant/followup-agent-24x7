"""Lead statuses, visit slots and contact normalization (pure domain)."""

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from followup_core.tenancy.domain.business_settings import ScheduleBlock
from inmo24x7_api.leads.domain.contact import normalize_contact
from inmo24x7_api.leads.domain.errors import InvalidLeadTransitionError, VisitCancelledError
from inmo24x7_api.leads.domain.lead import HandOffReason, Lead, LeadStatus, Visit, VisitStatus
from inmo24x7_api.leads.domain.notices import visit_confirmation
from inmo24x7_api.leads.domain.slots import propose_slots, short_slot_label, slot_label

BA = "America/Argentina/Buenos_Aires"
WEEKDAYS_9_18 = tuple(ScheduleBlock(day, time(9), time(18)) for day in range(5))
T0 = datetime(2026, 11, 3, 14, 0, tzinfo=UTC)


def _lead() -> Lead:
    return Lead.start(
        tenant_id=uuid4(),
        thread_id=uuid4(),
        thread_key="t:simulator:v.1",
        channel="simulator",
        is_test=True,
        now=T0,
    )


# --- Statuses ---------------------------------------------------------------------------


def test_a_new_lead_is_qualifying_with_its_history() -> None:
    lead = _lead()

    assert lead.status is LeadStatus.QUALIFYING
    assert [change.status for change in lead.history] == [LeadStatus.QUALIFYING]


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ([LeadStatus.VISIT_PROPOSED, LeadStatus.VISIT_CONFIRMED], True),
        ([LeadStatus.VISIT_PROPOSED, LeadStatus.HUMAN_REQUESTED], True),
        ([LeadStatus.HUMAN_REQUESTED, LeadStatus.VISIT_CONFIRMED], True),
        ([LeadStatus.HUMAN_REQUESTED, LeadStatus.VISIT_PROPOSED], False),
        ([LeadStatus.VISIT_CONFIRMED], False),
        ([LeadStatus.VISIT_PROPOSED, LeadStatus.QUALIFYING], False),
        # The team cancels a confirmed visit: back to human_requested to follow up.
        (
            [LeadStatus.VISIT_PROPOSED, LeadStatus.VISIT_CONFIRMED, LeadStatus.HUMAN_REQUESTED],
            True,
        ),
        (
            [LeadStatus.VISIT_PROPOSED, LeadStatus.VISIT_CONFIRMED, LeadStatus.VISIT_PROPOSED],
            False,
        ),
    ],
)
def test_transitions_are_enforced(path: list[LeadStatus], allowed: bool) -> None:
    lead = _lead()

    def walk() -> Lead:
        current = lead
        for step, status in enumerate(path, start=1):
            current = current.move_to(status, T0 + timedelta(minutes=step))
        return current

    if allowed:
        assert [c.status for c in walk().history][1:] == path
    else:
        with pytest.raises(InvalidLeadTransitionError):
            walk()


def test_moving_to_the_same_status_changes_nothing() -> None:
    lead = _lead()

    assert lead.move_to(LeadStatus.QUALIFYING, T0) is lead


def test_hand_off_happens_once_and_a_person_request_moves_the_status() -> None:
    lead = _lead().move_to(LeadStatus.VISIT_PROPOSED, T0).hand_off(HandOffReason.VISIT, T0)
    assert (lead.status, lead.hand_off_reason) == (LeadStatus.VISIT_PROPOSED, HandOffReason.VISIT)

    later = lead.hand_off(HandOffReason.HUMAN, T0 + timedelta(hours=1))

    assert later.status is LeadStatus.HUMAN_REQUESTED
    assert (later.handed_off_at, later.hand_off_reason) == (T0, HandOffReason.VISIT)


# --- Slots ------------------------------------------------------------------------------


def _local(slots: list[datetime]) -> list[str]:
    return [slot.astimezone(ZoneInfo(BA)).strftime("%a %d %H:%M") for slot in slots]


def test_slots_are_two_real_alternatives_at_least_three_hours_apart() -> None:
    # Tuesday 11:10 in Buenos Aires: 13:30 is the first free half hour, 16:30 the alternative.
    now = datetime(2026, 11, 3, 14, 10, tzinfo=UTC)

    assert _local(propose_slots(WEEKDAYS_9_18, BA, now)) == ["Tue 03 13:30", "Tue 03 16:30"]


def test_the_alternative_moves_to_the_next_day_when_the_day_ends_first() -> None:
    # Tuesday 13:00: the first slot is 15:00 and nothing 3 hours later fits before 18:00.
    now = datetime(2026, 11, 3, 16, 0, tzinfo=UTC)

    assert _local(propose_slots(WEEKDAYS_9_18, BA, now)) == ["Tue 03 15:00", "Wed 04 09:00"]


def test_slots_skip_closed_days_and_the_end_of_the_day() -> None:
    # Friday 16:00: 18:00 is closing time, so the next slots are on Monday.
    friday = datetime(2026, 11, 6, 19, 0, tzinfo=UTC)

    assert _local(propose_slots(WEEKDAYS_9_18, BA, friday)) == ["Mon 09 09:00", "Mon 09 12:00"]


def test_slots_are_only_proposed_inside_hours_even_after_hours() -> None:
    saturday_night = datetime(2026, 11, 8, 2, 0, tzinfo=UTC)  # Saturday 23:00 in BA

    slots = propose_slots(WEEKDAYS_9_18, BA, saturday_night)

    assert _local(slots) == ["Mon 09 09:00", "Mon 09 12:00"]
    assert all(slot > saturday_night for slot in slots)


def test_slots_use_the_tenant_timezone() -> None:
    now = datetime(2026, 11, 3, 6, 0, tzinfo=UTC)  # 03:00 in Buenos Aires, 07:00 in Madrid

    madrid = propose_slots(WEEKDAYS_9_18, "Europe/Madrid", now)
    buenos_aires = propose_slots(WEEKDAYS_9_18, BA, now)

    assert [s.isoformat() for s in madrid][0] == "2026-11-03T09:00:00+01:00"
    assert [s.isoformat() for s in buenos_aires][0] == "2026-11-03T09:00:00-03:00"


def test_a_slot_must_end_inside_the_block_and_split_blocks_work() -> None:
    hours = (ScheduleBlock(1, time(9), time(10)), ScheduleBlock(1, time(15), time(16)))
    now = datetime(2026, 11, 3, 11, 30, tzinfo=UTC)  # Tuesday 08:30: 10:30 is the earliest

    # 15:30 is too close to 15:00, so the alternative is the next Tuesday.
    assert _local(propose_slots(hours, BA, now)) == ["Tue 03 15:00", "Tue 10 09:00"]


def test_no_hours_means_no_slots() -> None:
    assert propose_slots((), BA, T0) == []


def test_slot_labels_are_in_spanish() -> None:
    start = datetime(2026, 11, 4, 10, 30, tzinfo=ZoneInfo(BA))

    assert slot_label(start) == "miércoles 4/11, 10:30"
    assert short_slot_label(start) == "mié 4/11 10:30"
    longest = datetime(2026, 12, 30, 18, 30, tzinfo=ZoneInfo(BA))
    assert len(short_slot_label(longest)) <= 20


# --- Contact ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("11 5555-1234", "+54 9 11 5555-1234"),
        ("011 15 5555-1234", "+54 9 11 5555-1234"),
        ("15 5555 1234", "+54 9 11 5555-1234"),
        ("+54 9 11 5555 1234", "+54 9 11 5555-1234"),
        ("+541155551234", "+54 9 11 5555-1234"),
        ("0341 15 456-7890", "+54 9 341 456-7890"),
        ("(0351) 456-7890", "+54 9 351 456-7890"),
        ("Ana@Example.com", "ana@example.com"),
        ("5555-1234", None),
        ("123", None),
        ("ana@", None),
        ("llamame mañana", None),
    ],
)
def test_contacts_are_validated_and_normalized(text: str, expected: str | None) -> None:
    assert normalize_contact(text) == expected


# --- Needs attention, visits and what the lead is told -------------------------------------


@pytest.mark.parametrize(
    ("status", "handed_off", "replied", "expected"),
    [
        (LeadStatus.HUMAN_REQUESTED, T0, None, True),
        (LeadStatus.VISIT_PROPOSED, T0, None, True),
        (LeadStatus.VISIT_PROPOSED, T0, T0 + timedelta(minutes=5), False),
        # A reply from before the hand-off does not count.
        (LeadStatus.VISIT_PROPOSED, T0, T0 - timedelta(minutes=5), True),
        (LeadStatus.VISIT_CONFIRMED, T0, None, False),
        (LeadStatus.QUALIFYING, None, None, False),
    ],
)
def test_needs_attention(status, handed_off, replied, expected) -> None:
    lead = replace(_lead(), status=status, handed_off_at=handed_off, last_human_reply_at=replied)

    assert lead.needs_attention is expected


def test_a_reply_from_the_team_takes_the_lead_out_of_attention() -> None:
    lead = _lead().move_to(LeadStatus.HUMAN_REQUESTED, T0).hand_off(HandOffReason.HUMAN, T0)

    assert lead.needs_attention
    assert not lead.replied_by_team(T0 + timedelta(minutes=1)).needs_attention


def _visit(status: VisitStatus = VisitStatus.PROPOSED) -> Visit:
    return Visit(uuid4(), uuid4(), None, "Depto · Gorriti 4800", T0, status, T0)


def test_confirming_a_visit_is_idempotent_and_can_change_the_time() -> None:
    confirmed = _visit().confirm()
    later = T0 + timedelta(days=1)

    assert confirmed.status is VisitStatus.CONFIRMED
    assert confirmed.confirm() == confirmed
    assert confirmed.confirm(later).starts_at == later
    assert _visit().cancel().status is VisitStatus.CANCELLED
    with pytest.raises(VisitCancelledError):
        _visit(VisitStatus.CANCELLED).confirm()


def test_the_confirmation_text_and_template_parameters() -> None:
    saturday = datetime(2026, 11, 7, 10, 30, tzinfo=ZoneInfo(BA))

    notice = visit_confirmation("Ana Pérez", "Gorriti 4800", saturday)
    anonymous = visit_confirmation(None, "Gorriti 4800", saturday)

    assert notice.text == (
        "¡Listo, Ana! Te confirmamos la visita a Gorriti 4800 el sábado 7/11 a las 10:30. "
        "Cualquier cosa, escribinos por acá."
    )
    assert notice.template_parameters == ("Ana", "Gorriti 4800", "sábado 7/11 a las 10:30")
    assert anonymous.text.startswith("¡Listo! Te confirmamos")
    assert anonymous.template_parameters[0] == "de nuevo"


def test_the_search_text_is_lowercase_without_accents_with_phone_digits() -> None:
    lead = replace(
        _lead(),
        visitor_name="Ana Pérez",
        contact="+54 9 11 5555-0188",
        answers={"zone": "Ñuñoa", "rooms": 2, "budget": {"amount": 1, "currency": "ARS"}},
    )

    assert lead.search_text == "ana perez +54 9 11 5555-0188 5491155550188 nunoa 2"
