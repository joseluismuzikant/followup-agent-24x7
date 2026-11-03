"""What the team's actions tell the lead and write in the transcript (Spanish, voseo)."""

from dataclasses import dataclass
from datetime import datetime

from .slots import day_label


def first_name(name: str | None) -> str | None:
    return name.split()[0] if name and name.split() else None


@dataclass(frozen=True, slots=True)
class VisitNotice:
    """A visit confirmation: free text inside the 24-hour window, or the approved template
    ("confirmacion_visita") with its three parameters outside it."""

    text: str
    template_parameters: tuple[str, str, str]


def visit_confirmation(name: str | None, address: str, starts_at_local: datetime) -> VisitNotice:
    first = first_name(name)
    day, time = day_label(starts_at_local), f"{starts_at_local:%H:%M}"
    greeting = f"¡Listo, {first}!" if first else "¡Listo!"
    text = (
        f"{greeting} Te confirmamos la visita a {address} el {day} a las {time}. "
        "Cualquier cosa, escribinos por acá."
    )
    # Meta rejects empty parameters: without a name the template reads "¡Hola de nuevo!".
    return VisitNotice(text, (first or "de nuevo", address, f"{day} a las {time}"))


def confirmed_visit(actor: str) -> str:
    return f"{actor} confirmó la visita"


def cancelled_visit(actor: str) -> str:
    return f"{actor} canceló la visita"
