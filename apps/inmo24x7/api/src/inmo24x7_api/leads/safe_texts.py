"""Fixed Spanish texts (voseo) for every reply intent.

Used when a reply must not come from the model: the output guard replaces a reply that
failed its checks, and a turn that hit a limit (or whose model is down) is worded with these
("degraded mode"). Placeholders are filled only from trusted facts the graph computed:
{option}, {options}, {slot}, {slots}, {requirement}, {question}, {agent}, {business}.
A placeholder without a value leaves the text without it (see `safe_text`).
"""

import re
from collections.abc import Mapping
from string import Formatter

from followup_core.conversation.domain.llm import ReplyIntent

DEFERRED_ANSWER = "Eso no lo tengo acá, lo consulto con el equipo y te aviso."
AGENT_FAILURE_TEXT = "Te paso con una persona del equipo, te escribe a la brevedad."
OFFER_HUMAN_TEXT = "¿Querés que te contacte una persona del equipo?"

SAFE_TEXTS: Mapping[ReplyIntent, str] = {
    ReplyIntent.GREET: "¡Hola! Soy {agent}, de {business}.",
    ReplyIntent.ASK: "Contame: ¿{question}?",
    ReplyIntent.PRESENT_OPTIONS: "Te comparto algunas opciones que pueden servirte.",
    ReplyIntent.NO_OPTIONS: "Por ahora no tengo opciones que coincidan; sigo buscando.",
    ReplyIntent.ASK_NAME: "¿Cómo te llamás?",
    ReplyIntent.ASK_CONTACT: "¿A qué teléfono o email te puede escribir alguien del equipo?",
    ReplyIntent.CLOSE: "¡Gracias! Alguien del equipo te va a contactar.",
    ReplyIntent.AFTER_CLOSE: "Ya le pasé tus datos al equipo.",
    ReplyIntent.INVALID_CONTACT: (
        "No pude tomar ese dato. ¿Me pasás un teléfono con código de área o un email?"
    ),
    ReplyIntent.OFFER_VISIT: "¿Querés visitar alguna? Decime cuál y te propongo horarios.",
    ReplyIntent.OFFER_SLOTS: "Para visitar {option} te propongo {slots}. ¿Cuál te queda mejor?",
    ReplyIntent.SLOT_CHOSEN: "Te anoté para el {slot}. El equipo te lo confirma.",
    ReplyIntent.HAND_OFF: "¡Gracias! Una persona del equipo sigue con tu consulta.",
    ReplyIntent.AFTER_HAND_OFF: "Ya le pasé tu consulta al equipo; te van a escribir pronto.",
    ReplyIntent.REQUIREMENT_CHECK: "Esta propiedad {requirement}. ¿Podrías cumplir con eso?",
    ReplyIntent.REQUIREMENT_CONFIRM: (
        "Para confirmar: esta propiedad {requirement}. ¿Te sirve igual, sí o no?"
    ),
    ReplyIntent.OFFER_FITTING: "Entonces te pueden servir {options}. ¿Querés visitar alguna?",
    ReplyIntent.ASK_RELAX: (
        "Por ahora las opciones que tenemos {requirement}. ¿Te interesaría verlas igual?"
    ),
    ReplyIntent.NO_FIT: (
        "¡Gracias por contarme! Por ahora no tengo opciones con esas condiciones; si entra "
        "algo, el equipo te avisa."
    ),
    ReplyIntent.ANSWER_QUESTION: DEFERRED_ANSWER,
    ReplyIntent.OFFER_HUMAN: OFFER_HUMAN_TEXT,
}

# What a text needs to make sense; without it, the plainer one is used.
_WITHOUT = {
    ReplyIntent.OFFER_SLOTS: "Te propongo coordinar la visita con el equipo.",
    ReplyIntent.SLOT_CHOSEN: "Anotado. El equipo te confirma el horario.",
    ReplyIntent.REQUIREMENT_CHECK: "Antes de coordinar, el equipo te cuenta los requisitos.",
    ReplyIntent.REQUIREMENT_CONFIRM: "Para confirmar: ¿te sirve igual, sí o no?",
    ReplyIntent.OFFER_FITTING: "Te pueden servir las otras opciones. ¿Querés visitar alguna?",
    ReplyIntent.ASK_RELAX: "¿Te interesaría ver otras opciones igual?",
    ReplyIntent.ASK: "Contame un poco más de lo que buscás.",
    ReplyIntent.GREET: "¡Hola!",
}
# A slot noted in the turn that hands off: one message says both.
SLOT_HAND_OFF = (
    "Te anoté para el {slot}. Una persona del equipo te lo confirma y sigue con tu consulta."
)


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def safe_text(
    intent: ReplyIntent,
    values: Mapping[str, str] | None = None,
    *,
    hand_off: bool = False,
) -> str:
    """The fixed text of `intent`, filled from `values`. Each value is put on one line and
    stripped of braces; a text whose placeholders are not all known falls back to a plainer
    one that needs none."""
    template = (
        SLOT_HAND_OFF if intent is ReplyIntent.SLOT_CHOSEN and hand_off else SAFE_TEXTS[intent]
    )
    clean = {
        key: re.sub(r"[{}]", "", " ".join(str(value).split()))
        for key, value in (values or {}).items()
        if value
    }
    if not _fields(template) <= set(clean):
        return _WITHOUT.get(intent, template.format_map({k: "" for k in _fields(template)}))
    text = template.format_map(clean)
    if intent is ReplyIntent.ASK:
        question = clean["question"]
        text = f"Contame: ¿{question[0].lower()}{question[1:]}?"
    return text
