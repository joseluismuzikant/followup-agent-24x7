"""Reminders without a database: the holidays, the sending calendar, which step comes next
and when, "Lo próximo", the templates' text and parameters, and the payment link token."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from cuentas_claras_api.payments.domain.requests import (
    PaymentRequest,
    TransferDetailsInvalidError,
    looks_like_token,
    new_token,
    token_hash,
    validate_transfer,
)
from cuentas_claras_api.reminders.domain.calendar import SendingCalendar
from cuentas_claras_api.reminders.domain.next_action import Connection, next_action
from cuentas_claras_api.reminders.domain.planning import (
    Hold,
    InvoiceState,
    plan,
    postponed,
    template_kind,
)
from cuentas_claras_api.reminders.domain.policy import (
    DEFAULT_WINDOW,
    ReminderPolicy,
    ReminderPolicyError,
    ReminderStep,
    SendWindow,
    StepKind,
    TemplateKind,
    WindowPreset,
)
from cuentas_claras_api.reminders.domain.templates import (
    DEFAULT_BODIES,
    InvoiceLine,
    TemplateError,
    WhatsAppTemplate,
    format_amount,
    format_due,
    positional,
    render,
    validate_body,
    values,
)
from cuentas_claras_api.reminders.infrastructure.holidays import (
    argentine_holidays,
    load_overrides,
    package_holidays,
)
from followup_core.tenancy.domain.business_settings import TEAM_HOURS_WEEKDAYS_9_18, ScheduleBlock

BA = "America/Argentina/Buenos_Aires"
TENANT = uuid4()

# Argentina's national holidays, written by hand. Fixed: Jan 1, Mar 24, Apr 2, May 1,
# May 25, Jun 20, Jul 9, Dec 8, Dec 25. Easter-based: Carnival (Mon and Tue, 48 and 47
# days before Easter), Maundy Thursday and Good Friday (Easter 2026: Apr 5; 2027: Mar 28).
# Movable (law 27.399: a Tuesday or Wednesday moves to the Monday before, a Thursday or
# Friday to the Monday after): Güemes (Jun 17), San Martín (Aug 17), Diversidad Cultural
# (Oct 12), Soberanía Nacional (Nov 20). Plus 2026's "días no laborables con fines
# turísticos" (decreed: Mar 23, Jul 10, Dec 7) and the Nov 9 2026 holiday for the Pope's
# visit. 2027's bridge days are not decreed yet (they go in holidays_ar.toml).
HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 2, 16),  # Carnaval
    date(2026, 2, 17),  # Carnaval
    date(2026, 3, 23),  # día no laborable con fines turísticos
    date(2026, 3, 24),
    date(2026, 4, 2),  # Malvinas and Maundy Thursday, the same day
    date(2026, 4, 3),  # Good Friday
    date(2026, 5, 1),
    date(2026, 5, 25),
    date(2026, 6, 15),  # Güemes: Wed Jun 17 moves to Mon Jun 15
    date(2026, 6, 20),
    date(2026, 7, 9),
    date(2026, 7, 10),  # día no laborable con fines turísticos
    date(2026, 8, 17),  # San Martín: already a Monday
    date(2026, 10, 12),  # already a Monday
    date(2026, 11, 9),  # the Pope's visit (decreed)
    date(2026, 11, 23),  # Soberanía: Fri Nov 20 moves to Mon Nov 23
    date(2026, 12, 7),  # día no laborable con fines turísticos
    date(2026, 12, 8),
    date(2026, 12, 25),
}
HOLIDAYS_2027 = {
    date(2027, 1, 1),
    date(2027, 2, 8),  # Carnaval (Easter Mar 28)
    date(2027, 2, 9),
    date(2027, 3, 24),
    date(2027, 3, 25),  # Maundy Thursday
    date(2027, 3, 26),  # Good Friday
    date(2027, 4, 2),
    date(2027, 5, 1),
    date(2027, 5, 25),
    date(2027, 6, 20),
    date(2027, 6, 21),  # Güemes: Thu Jun 17 moves to Mon Jun 21
    date(2027, 7, 9),
    date(2027, 8, 16),  # San Martín: Tue Aug 17 moves to Mon Aug 16
    date(2027, 10, 11),  # Diversidad Cultural: Tue Oct 12 moves to Mon Oct 11
    date(2027, 11, 20),  # Soberanía: a Saturday stays
    date(2027, 12, 8),
    date(2027, 12, 25),
}


def test_the_holidays_package_has_argentinas_2026_and_2027_holidays() -> None:
    assert set(package_holidays([2026])) == HOLIDAYS_2026
    assert set(package_holidays([2027])) == HOLIDAYS_2027
    assert argentine_holidays([2026, 2027]) == HOLIDAYS_2026 | HOLIDAYS_2027


def test_the_override_file_adds_and_removes_dates(tmp_path: Path) -> None:
    overrides = tmp_path / "holidays.toml"
    overrides.write_text('extra = [2027-04-01, "2027-07-12"]\nremoved = [2027-12-08]\n')

    days = argentine_holidays([2027], overrides)

    assert date(2027, 4, 1) in days and date(2027, 7, 12) in days
    assert date(2027, 12, 8) not in days
    assert load_overrides(tmp_path / "missing.toml").extra == frozenset()


def test_the_committed_override_file_parses() -> None:
    load_overrides()


def calendar(
    window: SendWindow = DEFAULT_WINDOW,
    holidays: frozenset[date] = frozenset(),
    team_hours: tuple[ScheduleBlock, ...] = TEAM_HOURS_WEEKDAYS_9_18,
) -> SendingCalendar:
    return SendingCalendar(BA, window, team_hours, holidays)


def ba(day: date, hour: int, minute: int = 0) -> datetime:
    return calendar().at(day, time(hour, minute)).astimezone(UTC)


MONDAY = date(2026, 11, 16)


def test_reminders_never_go_out_on_weekends_holidays_or_outside_the_window() -> None:
    days_off = calendar(holidays=frozenset({date(2026, 11, 23)}))

    assert days_off.next_sending_day(date(2026, 11, 21)) == date(2026, 11, 24)  # Sat → Tue
    assert days_off.next_sending_day(MONDAY) == MONDAY
    assert days_off.send_time(MONDAY, ba(MONDAY, 7)) == ba(MONDAY, 9)  # Mañanas 9–12
    assert days_off.send_time(MONDAY, ba(MONDAY, 10, 30)) == ba(MONDAY, 10, 30)
    assert days_off.send_time(MONDAY, ba(MONDAY, 12)) is None  # the window is over
    assert days_off.is_open(ba(MONDAY, 11, 59)) and not days_off.is_open(ba(MONDAY, 12))


def test_window_presets_and_the_team_hours() -> None:
    all_day = calendar(SendWindow(WindowPreset.BUSINESS_DAY))
    custom = calendar(SendWindow(WindowPreset.CUSTOM, time(14), time(16, 30)))
    team = calendar(
        SendWindow(WindowPreset.TEAM),
        team_hours=(ScheduleBlock(0, time(8), time(12)), ScheduleBlock(5, time(9), time(13))),
    )

    assert all_day.ranges(MONDAY) == [(time(9), time(18))]
    assert custom.send_time(MONDAY, ba(MONDAY, 10)) == ba(MONDAY, 14)
    assert team.ranges(MONDAY) == [(time(8), time(12))]
    # The team works on Saturdays, but reminders never go out on a weekend.
    assert team.ranges(date(2026, 11, 21)) == []
    assert team.next_sending_day(date(2026, 11, 17)) == date(2026, 11, 23)


@pytest.mark.parametrize(
    ("start", "end"), [(time(5), time(9)), (time(12), time(11)), (time(9), time(23))]
)
def test_a_custom_window_is_between_6_and_22(start: time, end: time) -> None:
    with pytest.raises(ReminderPolicyError):
        SendWindow(WindowPreset.CUSTOM, start, end)


def test_the_default_policy_and_its_rules() -> None:
    policy = ReminderPolicy.default(TENANT)

    assert [step.offset_days for step in policy.steps] == [-3, 0, 7, 15]
    assert [step.template_kind for step in policy.steps] == [
        TemplateKind.BEFORE,
        TemplateKind.DUE,
        TemplateKind.AFTER,
        None,
    ]
    assert policy.steps[-1].escalates
    assert policy.window.preset is WindowPreset.MORNINGS
    assert policy.skip_holidays and policy.pause_on_promise


@pytest.mark.parametrize(
    ("steps", "field"),
    [
        ([ReminderStep(0), ReminderStep(0)], "offset_duplicate"),
        ([ReminderStep(-31)], "offset_range"),
        ([ReminderStep(91)], "offset_range"),
        ([ReminderStep(20, StepKind.ESCALATE), ReminderStep(30)], "escalation_last"),
        ([], "steps"),
    ],
)
def test_invalid_policies(steps: list[ReminderStep], field: str) -> None:
    with pytest.raises(ReminderPolicyError) as error:
        ReminderPolicy(TENANT, tuple(steps))
    assert error.value.field == field


POLICY = ReminderPolicy.default(TENANT)
BEFORE, DUE, AFTER, ESCALATE = POLICY.steps


def state(due: date, promised_until: date | None = None) -> InvoiceState:
    return InvoiceState(uuid4(), uuid4(), due, promised_until)


def test_each_step_is_planned_for_its_day() -> None:
    due = date(2026, 11, 19)  # a Thursday
    cal = calendar()

    assert plan(state(due), POLICY, set(), date(2026, 11, 10), cal).day == date(2026, 11, 16)
    on_the_day = plan(state(due), POLICY, set(), date(2026, 11, 16), cal)
    assert (on_the_day.step, on_the_day.due_on(date(2026, 11, 16))) == (BEFORE, True)
    after_before = plan(state(due), POLICY, {BEFORE.id}, date(2026, 11, 16), cal)
    assert (after_before.step, after_before.day) == (DUE, due)


def test_a_step_on_a_weekend_or_holiday_goes_out_the_next_sending_day_never_earlier() -> None:
    due = date(2026, 11, 26)  # a Thursday; -3 is Monday the 23rd, a holiday
    cal = calendar(holidays=frozenset({date(2026, 11, 23)}))

    planned = plan(state(due), POLICY, set(), date(2026, 11, 20), cal)

    assert (planned.step, planned.day) == (BEFORE, date(2026, 11, 24))


def test_an_invoice_imported_late_gets_the_latest_step_not_the_old_ones() -> None:
    due = MONDAY - timedelta(days=10)
    planned = plan(state(due), POLICY, set(), MONDAY, calendar())

    assert (planned.step, planned.day) == (AFTER, MONDAY)


def test_escalation_waits_for_one_reminder_unless_the_client_cannot_get_any() -> None:
    due = MONDAY - timedelta(days=60)

    first = plan(state(due), POLICY, set(), MONDAY, calendar())
    then = plan(state(due), POLICY, {AFTER.id}, MONDAY, calendar())
    unreachable = plan(state(due), POLICY, set(), MONDAY, calendar(), reachable=False)
    done = plan(state(due), POLICY, {AFTER.id, ESCALATE.id}, MONDAY, calendar())

    assert first.step == AFTER
    assert then.step == ESCALATE and then.due_on(MONDAY)
    assert unreachable.step == ESCALATE
    assert done.hold is Hold.ESCALATED


def test_a_promise_pauses_and_the_day_after_the_next_pending_step_goes_out() -> None:
    due = MONDAY - timedelta(days=1)
    promised = state(due, promised_until=MONDAY + timedelta(days=2))

    paused = plan(promised, POLICY, {BEFORE.id}, MONDAY, calendar())
    resumed = plan(promised, POLICY, {BEFORE.id}, MONDAY + timedelta(days=3), calendar())
    ignored = plan(
        promised,
        ReminderPolicy(TENANT, POLICY.steps, pause_on_promise=False),
        {BEFORE.id},
        MONDAY,
        calendar(),
    )

    assert (paused.hold, paused.until) == (Hold.PROMISED, MONDAY + timedelta(days=2))
    assert resumed.step == DUE and resumed.due_on(MONDAY + timedelta(days=3))
    assert ignored.step == DUE


def test_steps_turned_off_or_all_done() -> None:
    off = ReminderPolicy(
        TENANT, tuple(ReminderStep(s.offset_days, s.kind, False) for s in POLICY.steps)
    )
    no_escalation = ReminderPolicy(TENANT, (ReminderStep(-3), ReminderStep(0)))
    late = MONDAY - timedelta(days=5)

    assert plan(state(MONDAY), off, set(), MONDAY, calendar()).hold is Hold.NO_STEPS
    finished = plan(state(late), no_escalation, {POLICY.steps[0].id}, MONDAY, calendar())
    assert finished.step is not None  # its due-date step is still pending
    all_done = {step.id for step in no_escalation.steps}
    assert plan(state(late), no_escalation, all_done, MONDAY, calendar()).hold is Hold.FINISHED


def test_one_reminder_per_client_per_day_moves_the_next_one_to_the_next_sending_day() -> None:
    friday = date(2026, 11, 20)
    cal = calendar(holidays=frozenset({date(2026, 11, 23)}))
    planned = plan(state(friday), POLICY, {BEFORE.id}, friday, cal)

    moved = postponed(planned, friday, cal)

    assert planned.day == friday and moved.day == date(2026, 11, 24)  # Mon 23 is a holiday
    assert moved.step == DUE


def test_a_late_reminder_says_what_is_true_on_the_day_it_goes_out() -> None:
    due = date(2026, 11, 21)  # a Saturday: the due-date step goes out on Monday

    assert template_kind(DUE, due, due) is TemplateKind.DUE
    assert template_kind(DUE, due, date(2026, 11, 23)) is TemplateKind.AFTER
    assert template_kind(BEFORE, due, date(2026, 11, 19)) is TemplateKind.BEFORE


def test_lo_proximo() -> None:
    cal = calendar()
    now = ba(MONDAY, 8)
    approved = {TemplateKind.BEFORE, TemplateKind.DUE, TemplateKind.AFTER}

    def label(planned, **kwargs) -> str:
        options = {
            "due_date": MONDAY,
            "has_whatsapp": True,
            "opted_out": False,
            "connection": Connection.OK,
            "approved": approved,
            "calendar": cal,
            "now": now,
        }
        return next_action(planned, **(options | kwargs)).label

    today = plan(state(MONDAY), POLICY, {BEFORE.id}, MONDAY, cal)
    tomorrow = plan(state(MONDAY + timedelta(days=4)), POLICY, set(), MONDAY, cal)
    later = plan(state(MONDAY + timedelta(days=10)), POLICY, set(), MONDAY, cal)

    assert label(today) == "Recordatorio hoy 9:00"
    assert label(tomorrow, due_date=MONDAY + timedelta(days=4)) == "Recordatorio mañana 9:00"
    assert label(later, due_date=MONDAY + timedelta(days=10)) == "Recordatorio el 23/11 9:00"
    assert label(today, now=ba(MONDAY, 13)) == "Recordatorio mañana 9:00"
    assert label(today, has_whatsapp=False) == "Sin WhatsApp"
    assert label(today, connection=Connection.NONE) == "Falta conectar WhatsApp"
    assert label(today, connection=Connection.ERROR) == "Pausado: WhatsApp desconectado"
    assert label(today, approved=set()) == "En espera: plantilla en revisión"
    promised = plan(state(MONDAY, MONDAY + timedelta(days=4)), POLICY, set(), MONDAY, cal)
    assert label(promised) == "Pausado: promesa hasta 20/11"
    escalated = plan(state(MONDAY), POLICY, {ESCALATE.id}, MONDAY, cal)
    assert label(escalated) == "Escalado al dueño"


@pytest.mark.parametrize(
    ("amount", "currency", "text"),
    [
        ("1234.56", "ARS", "$ 1.234,56"),
        ("180000", "ARS", "$ 180.000,00"),
        ("0.5", "ARS", "$ 0,50"),
        ("1234567.891", "ARS", "$ 1.234.567,89"),
        ("950", "USD", "US$ 950,00"),
    ],
)
def test_amounts_are_formatted_the_argentine_way(amount: str, currency: str, text: str) -> None:
    assert format_amount(Decimal(amount), currency) == text


def test_due_dates_are_dd_mm() -> None:
    assert format_due(date(2026, 3, 5)) == "05/03"


def test_one_message_for_several_invoices_lists_them_with_the_total() -> None:
    lines = [
        InvoiceLine("B 0003-00001245", Decimal("180000"), "ARS", date(2026, 11, 20)),
        InvoiceLine("B 0003-00001246", Decimal("95500.50"), "ARS", date(2026, 11, 15)),
    ]

    fields = values("Edificio  Güemes", "Ascensores Delta", lines)

    assert fields == {
        "cliente": "Edificio Güemes",
        "negocio": "Ascensores Delta",
        "factura": "B 0003-00001245, B 0003-00001246",
        "monto": "$ 275.500,50",
        "vencimiento": "15/11",
    }


def test_the_default_texts_are_valid_and_become_meta_variables() -> None:
    for kind, body in DEFAULT_BODIES.items():
        assert validate_body(body) == body, kind
    assert positional("Hola {cliente}, la {factura} vence el {vencimiento}.") == (
        "Hola {{1}}, la {{2}} vence el {{3}}."
    )


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ("{cliente}, te escribimos.", "field_at_edge"),
        ("Hola, vence el {vencimiento}.", "field_at_edge"),
        ("Hola {cliente} {negocio} te escribimos.", "adjacent_fields"),
        ("Hola {cliente}, {cliente} otra vez.", "repeated_field"),
        ("Hola {nombre}, te escribimos.", "unknown_field"),
        ("Hola {cliente}, te escribimos {.", "braces"),
        ("", "body"),
        ("x" * 1025, "body"),
    ],
)
def test_invalid_template_texts(body: str, field: str) -> None:
    with pytest.raises(TemplateError) as error:
        validate_body(body)
    assert error.value.field == field


def test_the_template_meta_gets_and_the_message_it_sends() -> None:
    now = datetime(2026, 11, 11, tzinfo=UTC)
    template = WhatsAppTemplate.new(
        TENANT, TemplateKind.DUE, 2, DEFAULT_BODIES[TemplateKind.DUE], now
    )
    fields = values(
        "Edificio Güemes",
        "Ascensores Delta",
        [InvoiceLine("B 0003-00001245", Decimal("180000"), "ARS", date(2026, 11, 16))],
    )

    request = template.meta_request("https://cuentasclaras.example.com/", "Ascensores Delta")
    message = template.message_body(fields, "tok123")

    assert template.name == "cuentas_claras_vence_hoy_v2"
    assert (request["category"], request["language"]) == ("UTILITY", "es_AR")
    body, buttons = request["components"]
    assert body["text"].startswith("Hola {{1}}, te escribimos de {{2}}. Hoy vence la factura {{3}}")
    assert len(body["example"]["body_text"][0]) == 4
    assert buttons["buttons"][0]["url"] == "https://cuentasclaras.example.com/p/{{1}}"
    parameters, button = message["template"]["components"]
    assert [item["text"] for item in parameters["parameters"]] == [
        "Edificio Güemes",
        "Ascensores Delta",
        "B 0003-00001245",
        "$ 180.000,00",
    ]
    assert button == {
        "type": "button",
        "sub_type": "url",
        "index": "0",
        "parameters": [{"type": "text", "text": "tok123"}],
    }
    assert render(template.body, fields).startswith("Hola Edificio Güemes, te escribimos de")


def test_payment_link_tokens_are_long_random_and_url_safe() -> None:
    tokens = {new_token() for _ in range(200)}
    now = datetime(2026, 11, 11, tzinfo=UTC)

    request, token = PaymentRequest.create(TENANT, uuid4(), [uuid4(), uuid4()], now)

    assert len(tokens) == 200
    assert all(len(token) >= 43 and looks_like_token(token) for token in tokens)  # 256 bits
    assert request.token_hash == token_hash(token) and token not in request.token_hash
    assert request.expires_at == now + timedelta(days=60)
    assert not looks_like_token("../../etc/passwd") and not looks_like_token("short")


def test_transfer_details() -> None:
    assert validate_transfer(TENANT, "0000003100012345678901", " Ana  Pérez ", None).holder == (
        "Ana Pérez"
    )
    assert validate_transfer(TENANT, "ascensores.delta", "Ana", "Galicia").cbu_or_alias
    with pytest.raises(TransferDetailsInvalidError):
        validate_transfer(TENANT, "123", "Ana", None)
