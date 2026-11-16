""" "Lo próximo" (C2 and the invoice drawer): the next scheduled action for an owed invoice,
in a few words ("Recordatorio mañana 9:30", "Pausado: promesa hasta 15/11", "Escalado al
dueño", "Sin WhatsApp")."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from .calendar import SendingCalendar
from .planning import Hold, Plan, template_kind
from .policy import TemplateKind


class ActionKind(StrEnum):
    REMINDER = "reminder"
    ESCALATION = "escalation"
    PROMISED = "promised"
    ESCALATED = "escalated"
    NO_WHATSAPP = "no_whatsapp"
    OPTED_OUT = "opted_out"
    NOT_CONNECTED = "not_connected"
    CONNECTION_ERROR = "connection_error"
    TEMPLATE_PENDING = "template_pending"
    FINISHED = "finished"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class NextAction:
    kind: ActionKind
    label: str
    at: datetime | None = None


class Connection(StrEnum):
    OK = "ok"
    NONE = "none"
    ERROR = "error"  # sending stopped (revoked token, ...)


def clock_label(moment: datetime) -> str:
    return f"{moment.hour}:{moment.minute:02d}"


def day_label(day: date, today: date) -> str:
    if day == today:
        return "hoy"
    if day == today + timedelta(days=1):
        return "mañana"
    return f"el {day:%d/%m}"


def next_action(
    plan: Plan,
    *,
    due_date: date,
    has_whatsapp: bool,
    opted_out: bool,
    connection: Connection,
    approved: Collection[TemplateKind],
    calendar: SendingCalendar,
    now: datetime,
) -> NextAction:
    today = calendar.today(now)
    if plan.hold is Hold.ESCALATED:
        return NextAction(ActionKind.ESCALATED, "Escalado al dueño")
    if plan.hold is Hold.PROMISED and plan.until is not None:
        return NextAction(ActionKind.PROMISED, f"Pausado: promesa hasta {plan.until:%d/%m}")
    if plan.hold is Hold.NO_STEPS:
        return NextAction(ActionKind.OFF, "Recordatorios apagados")
    if plan.hold in (Hold.FINISHED, Hold.NO_SENDING_DAY) or plan.step is None:
        return NextAction(ActionKind.FINISHED, "Sin más recordatorios")
    assert plan.day is not None
    day = max(plan.day, today)
    if plan.step.escalates:
        return NextAction(
            ActionKind.ESCALATION,
            f"Aviso al dueño {day_label(day, today)}",
            calendar.at(day, datetime.min.time()),
        )
    if opted_out:
        return NextAction(ActionKind.OPTED_OUT, "Sin recordatorios (pedido del cliente)")
    if not has_whatsapp:
        return NextAction(ActionKind.NO_WHATSAPP, "Sin WhatsApp")
    if connection is Connection.NONE:
        return NextAction(ActionKind.NOT_CONNECTED, "Falta conectar WhatsApp")
    if connection is Connection.ERROR:
        return NextAction(ActionKind.CONNECTION_ERROR, "Pausado: WhatsApp desconectado")
    moment = calendar.send_time(day, now)
    if moment is None:
        following = calendar.next_sending_day(day + timedelta(days=1))
        if following is None:
            return NextAction(ActionKind.FINISHED, "Sin más recordatorios")
        day = following
        moment = calendar.window_start(day)
        assert moment is not None
    if template_kind(plan.step, due_date, day) not in approved:
        return NextAction(ActionKind.TEMPLATE_PENDING, "En espera: plantilla en revisión")
    return NextAction(
        ActionKind.REMINDER,
        f"Recordatorio {day_label(day, today)} {clock_label(moment)}",
        moment,
    )
