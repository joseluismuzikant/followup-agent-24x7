"""A deterministic LanguageModel for tests and for local development without an API key.

Extraction uses simple keyword and regex rules; replies come from templates per tone.
`fail_with` makes every call raise, to exercise the "agent unavailable" path.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from followup_core.tenancy.domain.agent_config import QualificationQuestion, QuestionKind, Tone

from ..domain.answers import normalize
from ..domain.errors import LlmUnavailableError
from ..domain.llm import (
    CONTACT_KEY,
    NAME_KEY,
    Choice,
    Extraction,
    ExtractionRequest,
    Reply,
    ReplyIntent,
    ReplyRequest,
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"\+?\d[\d\s-]{6,}\d")
_WORD = r"[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+"
_NAME = re.compile(rf"\b(?i:me llamo|mi nombre es|soy)\s+({_WORD}(?: {_WORD})?)")
_PLACE = re.compile(rf"\ben\s+({_WORD}(?: {_WORD})*)")
_ROOMS = re.compile(r"(\d+)\s*amb")
_AMOUNT = re.compile(r"(\d[\d.,]*)\s*(mil|k)?\b", re.IGNORECASE)
_USD = re.compile(r"\b(usd|u\$s|d[oó]lares?)\b|us\$", re.IGNORECASE)
_ARS = re.compile(r"\$|\bpesos\b|\bars\b", re.IGNORECASE)
_YES = ("si", "claro", "tengo", "obvio", "dale")
_HUMAN = re.compile(
    r"\b(?:hablar|comunicarme|contactarme|atender(?:me)?)\s+(?:con\s+)?"
    r"(?:alguien|una persona|un humano|un asesor|una asesora|un vendedor|el equipo)\b"
    r"|\bpersona real\b|\bun humano\b"
)
_ORDINALS = (
    re.compile(r"\b(?:primer[ao]?|(?:la|el|opcion|numero)\s*1)\b"),
    re.compile(r"\b(?:segund[ao]|(?:la|el|opcion|numero)\s*2)\b"),
    re.compile(r"\b(?:tercer[ao]?|(?:la|el|opcion|numero)\s*3)\b"),
)
# Words too common in listing labels to identify one of them.
_COMMON = frozenset({"ambientes", "ambiente", "con", "del", "luminoso", "reciclado", "frente"})


def _choice_id(choices: Sequence[Choice], text: str) -> str | None:
    """Exact label, then ordinal ("la segunda"), then a distinctive word of one label
    (a street name). None when nothing or more than one choice matches."""
    if not choices:
        return None
    said = normalize(text)
    exact = [choice for choice in choices if normalize(choice.label) == said]
    if len(exact) == 1:
        return exact[0].id
    for index, pattern in enumerate(_ORDINALS[: len(choices)]):
        if pattern.search(said):
            return choices[index].id
    words = set(re.findall(r"[a-z]{4,}", said))
    matches = [
        choice
        for choice in choices
        if words & (set(re.findall(r"[a-z]{4,}", normalize(choice.label))) - _COMMON)
    ]
    return matches[0].id if len(matches) == 1 else None


def _money(text: str, asked: bool) -> dict[str, Any] | None:
    currency = "USD" if _USD.search(text) else "ARS" if _ARS.search(text) else None
    if currency is None and not asked:
        return None
    match = _AMOUNT.search(text)
    if not match:
        return None
    amount = int(re.sub(r"[.,]", "", match.group(1)))
    if match.group(2):
        amount *= 1000
    return {"amount": amount, "currency": currency or "ARS"}


def _choice(question: QualificationQuestion, text: str) -> str | None:
    words = normalize(text).split()
    matches = [
        option
        for option in question.options
        if any(word.startswith(normalize(option)[:5]) for word in words)
    ]
    return matches[0] if len(matches) == 1 else None


def _value(question: QualificationQuestion, text: str, asked: bool) -> Any:
    match question.kind:
        case QuestionKind.CHOICE:
            return _choice(question, text)
        case QuestionKind.MONEY:
            return _money(text, asked)
        case QuestionKind.NUMBER:
            rooms = _ROOMS.search(text)
            if rooms:
                return int(rooms.group(1))
            number = re.search(r"\d+", text)
            return int(number.group(0)) if asked and number else None
        case QuestionKind.BOOLEAN:
            if not asked:
                return None
            first = normalize(text).split()[:1]
            if first and first[0] in _YES:
                return True
            return False if first and first[0] == "no" else None
        case QuestionKind.TEXT:
            if asked:
                return text.strip()
            place = _PLACE.search(text)
            return place.group(1) if place else None


_GREETINGS = {
    Tone.WARM: "¡Hola! Soy {agent}, de {business}. Te ayudo a encontrar tu próxima propiedad.",
    Tone.PROFESSIONAL: "Hola, soy {agent}, de {business}. Voy a ayudarte con tu búsqueda.",
    Tone.FORMAL: (
        "Buen día. Mi nombre es {agent}, de {business}, y voy a acompañarte en tu búsqueda."
    ),
}
# The greeting when the lead already said what they look for: introduce, then acknowledge.
_LOOKING_FOR = {
    Tone.WARM: "¡Hola! Soy {agent}, de {business}. Buenísimo, te busco opciones de {looking_for}.",
    Tone.PROFESSIONAL: "Hola, soy {agent}, de {business}. Te busco opciones de {looking_for}.",
    Tone.FORMAL: (
        "Buen día. Mi nombre es {agent}, de {business}. Le busco opciones de {looking_for}."
    ),
}
_QUESTION_PREFIX = {
    Tone.WARM: "Contame: ¿{label}?",
    Tone.PROFESSIONAL: "¿{label}?",
    Tone.FORMAL: "¿Me podrías indicar {label}?",
}
_TEMPLATES: dict[ReplyIntent, dict[Tone, str]] = {
    ReplyIntent.PRESENT_OPTIONS: {
        Tone.WARM: "¡Mirá estas opciones que te pueden gustar!",
        Tone.PROFESSIONAL: "Te comparto algunas opciones que coinciden con tu búsqueda.",
        Tone.FORMAL: "Le comparto algunas opciones que coinciden con su búsqueda.",
    },
    ReplyIntent.NO_OPTIONS: {
        Tone.WARM: "Todavía no tengo algo justo para vos, pero sigo buscando.",
        Tone.PROFESSIONAL: "Por ahora no tengo opciones que coincidan.",
        Tone.FORMAL: "Por el momento no contamos con opciones que coincidan.",
    },
    ReplyIntent.ASK_NAME: {
        Tone.WARM: "¿Cómo te llamás?",
        Tone.PROFESSIONAL: "¿Me decís tu nombre?",
        Tone.FORMAL: "¿Me podrías indicar tu nombre?",
    },
    ReplyIntent.ASK_CONTACT: {
        Tone.WARM: "¿A qué teléfono o email te puede escribir alguien del equipo?",
        Tone.PROFESSIONAL: "¿Me pasás un teléfono o email de contacto?",
        Tone.FORMAL: "¿Me podrías indicar un teléfono o email de contacto?",
    },
    ReplyIntent.CLOSE: {
        Tone.WARM: "¡Gracias{name}! Alguien del equipo te va a contactar muy pronto.",
        Tone.PROFESSIONAL: "Gracias{name}. Alguien del equipo te va a contactar.",
        Tone.FORMAL: (
            "Muchas gracias{name}. Una persona del equipo se va a comunicar a la brevedad."
        ),
    },
    ReplyIntent.AFTER_CLOSE: {
        Tone.WARM: "¡Ya le pasé tus datos al equipo! Te van a escribir pronto.",
        Tone.PROFESSIONAL: "Ya le pasé tus datos al equipo.",
        Tone.FORMAL: "Sus datos ya fueron enviados al equipo.",
    },
    ReplyIntent.INVALID_CONTACT: {
        Tone.WARM: "Mmm, no me quedó claro. ¿Me pasás un teléfono con código de área o un email?",
        Tone.PROFESSIONAL: (
            "No pude tomar ese dato. ¿Me pasás un teléfono con código de área o un email?"
        ),
        Tone.FORMAL: (
            "No pude registrar ese dato. "
            "¿Me podría indicar un teléfono con código de área o un email?"
        ),
    },
    ReplyIntent.OFFER_VISIT: {
        Tone.WARM: "¿Te gustaría visitar alguna? Decime cuál y te propongo horarios.",
        Tone.PROFESSIONAL: "¿Querés visitar alguna? Decime cuál y te propongo horarios.",
        Tone.FORMAL: "¿Desea visitar alguna? Indíqueme cuál y le propongo horarios.",
    },
    ReplyIntent.OFFER_SLOTS: {
        Tone.WARM: "¡Buenísimo! Para ver {option} te propongo {slots}. ¿Cuál te queda mejor?",
        Tone.PROFESSIONAL: "Para visitar {option} tengo {slots}. ¿Cuál preferís?",
        Tone.FORMAL: "Para visitar {option} le propongo {slots}. ¿Cuál prefiere?",
    },
    ReplyIntent.SLOT_CHOSEN: {
        Tone.WARM: "¡Listo! Te anoté para el {slot}. El equipo te lo confirma.",
        Tone.PROFESSIONAL: "Anotado para el {slot}. El equipo te lo confirma.",
        Tone.FORMAL: "Queda registrado para el {slot}. El equipo se lo confirmará.",
    },
    ReplyIntent.HAND_OFF: {
        Tone.WARM: (
            "¡Gracias{name}! Le paso tu consulta a una persona del equipo, "
            "que te va a escribir muy pronto."
        ),
        Tone.PROFESSIONAL: "Gracias{name}. Una persona del equipo sigue con tu consulta.",
        Tone.FORMAL: "Muchas gracias{name}. Una persona del equipo continuará con su consulta.",
    },
    ReplyIntent.AFTER_HAND_OFF: {
        Tone.WARM: (
            "Ya le pasé tu consulta al equipo, te escriben muy pronto. ¡Gracias por la paciencia!"
        ),
        Tone.PROFESSIONAL: "Ya le pasé tu consulta al equipo; te van a escribir pronto.",
        Tone.FORMAL: "Su consulta ya fue derivada al equipo, que se comunicará a la brevedad.",
    },
}
# A slot noted in the turn that also hands off: one message says both.
_SLOT_HAND_OFF = {
    Tone.WARM: (
        "¡Listo{name}! Te anoté para el {slot}. Una persona del equipo te lo confirma "
        "y sigue con tu consulta muy pronto."
    ),
    Tone.PROFESSIONAL: (
        "Anotado para el {slot}{name}. Una persona del equipo te lo confirma y sigue con tu "
        "consulta."
    ),
    Tone.FORMAL: (
        "Queda registrado para el {slot}{name}. Una persona del equipo se lo confirmará y "
        "continuará con su consulta."
    ),
}
_AFTER_HOURS = {
    Tone.WARM: " Ahora el equipo no está, así que te lo confirman apenas vuelvan.",
    Tone.PROFESSIONAL: " El equipo lo confirma cuando vuelva a estar disponible.",
    Tone.FORMAL: " El equipo se lo confirmará en su próximo horario de atención.",
}


class FakeLanguageModel:
    def __init__(self, fail_with: Exception | None = None) -> None:
        self.fail_with = fail_with
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "fake"

    @property
    def prompt_versions(self) -> Mapping[str, str]:
        return {"extract": "fake", "reply": "fake"}

    def _call(self) -> None:
        self.calls += 1
        if self.fail_with is not None:
            raise LlmUnavailableError("Fake model failure.") from self.fail_with

    def extract(self, request: ExtractionRequest) -> Extraction:
        self._call()
        text = request.latest
        values = {
            question.key: value
            for question in request.questions
            if (value := _value(question, text, request.asked_key == question.key)) is not None
        }
        name = None
        if request.wants_name:
            match = _NAME.search(text)
            if match:
                name = match.group(1)
            elif request.asked_key == NAME_KEY and not _EMAIL.search(text):
                name = " ".join(text.strip().split()[:2]).title() or None
        contact = None
        if request.wants_contact or request.asked_key == CONTACT_KEY:
            match = _EMAIL.search(text) or _PHONE.search(text)
            contact = match.group(0).strip() if match else None
        return Extraction(
            values=values,
            visitor_name=name,
            contact=contact,
            choice_id=_choice_id(request.choices, text),
            wants_human=bool(_HUMAN.search(normalize(text))),
        )

    def compose_reply(self, request: ReplyRequest) -> Reply:
        self._call()
        tone = request.tone
        question = request.question
        asked = ""
        if question is not None:
            label = question.label[0].lower() + question.label[1:]
            asked = _QUESTION_PREFIX[tone].format(label=label)
            if question.options:
                asked += f" ({' / '.join(question.options)})"
        if request.intent is ReplyIntent.GREET:
            looking_for = request.facts.get("looking_for")
            greeting = (_LOOKING_FOR if looking_for else _GREETINGS)[tone].format(
                agent=request.agent_name, business=request.business_name, looking_for=looking_for
            )
            # Without a question the greeting asks nothing: the next message does.
            return Reply(f"{greeting} {asked}".strip())
        if request.intent is ReplyIntent.ASK:
            return Reply(asked)
        facts = dict(request.facts)
        name = facts.get("visitor_name")
        template = _TEMPLATES[request.intent][tone]
        if request.intent is ReplyIntent.SLOT_CHOSEN and facts.get("hand_off"):
            template = _SLOT_HAND_OFF[tone]
        text = template.format(
            name=f", {name}" if name else "",
            option=facts.get("option", "esa propiedad"),
            slots=facts.get("slots", ""),
            slot=facts.get("slot", ""),
        )
        if request.intent is ReplyIntent.OFFER_SLOTS and facts.get("after_hours"):
            text += _AFTER_HOURS[tone]
        return Reply(text)
