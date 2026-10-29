"""A deterministic LanguageModel for tests and for local development without an API key.

Extraction uses simple keyword and regex rules; replies come from templates per tone.
`fail_with` makes every call raise, to exercise the "agent unavailable" path.
"""

import re
from collections.abc import Mapping
from typing import Any

from followup_core.tenancy.domain.agent_config import QualificationQuestion, QuestionKind, Tone

from ..domain.answers import normalize
from ..domain.errors import LlmUnavailableError
from ..domain.llm import (
    CONTACT_KEY,
    NAME_KEY,
    Extraction,
    ExtractionRequest,
    Reply,
    ReplyIntent,
    ReplyRequest,
)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"\+?\d[\d\s-]{6,}\d")
_WORD = r"[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+"
_NAME = re.compile(rf"\b(?:me llamo|mi nombre es|soy)\s+({_WORD}(?: {_WORD})?)")
_PLACE = re.compile(rf"\ben\s+({_WORD}(?: {_WORD})*)")
_ROOMS = re.compile(r"(\d+)\s*amb")
_AMOUNT = re.compile(r"(\d[\d.,]*)\s*(mil|k)?\b", re.IGNORECASE)
_USD = re.compile(r"\b(usd|u\$s|d[oó]lares?)\b|us\$", re.IGNORECASE)
_ARS = re.compile(r"\$|\bpesos\b|\bars\b", re.IGNORECASE)
_YES = ("si", "claro", "tengo", "obvio", "dale")


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
        return Extraction(values=values, visitor_name=name, contact=contact)

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
            greeting = _GREETINGS[tone].format(
                agent=request.agent_name, business=request.business_name
            )
            return Reply(f"{greeting} {asked}".strip())
        if request.intent is ReplyIntent.ASK:
            return Reply(asked)
        name = request.facts.get("visitor_name")
        return Reply(_TEMPLATES[request.intent][tone].format(name=f", {name}" if name else ""))
