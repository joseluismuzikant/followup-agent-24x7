"""The lead's situation as the conversation learns it, and what Sofía still needs to know
before booking a visit to a property.

- **Facts** are captured whenever the lead mentions them, never guessed and never asked up
  front ("tengo un perro", "es para mi consultorio", "lo quiero por 6 meses").
- **Active questions** (in Agente → Preguntas, each can be turned off) are asked only when
  the lead chooses a property and that property needs the answer: rent → the guarantee (if
  it lists accepted guarantees) and the term (if it has a minimum or takes no temporary
  rentals); sale → credit (if `apto_credito` is known). One per message, as always.
- **Confirmations** are the lead's answer to "Esta propiedad pide X. ¿Podrías conseguirlo?"
  and to the "nothing fits" question.

Never ask income, salary amounts or other financial details: for "recibo de sueldo" only
whether they have one.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from followup_core.conversation.domain.answers import normalize
from followup_core.tenancy.domain.agent_config import QualificationQuestion, QuestionKind

from ..properties.domain.conditions import (
    LEAD_GUARANTEES,
    LeadConditions,
    PropertyConditions,
)
from ..properties.domain.operation import Operation

GARANTIA = "garantia"
PLAZO_MESES = "plazo_meses"
NECESITA_CREDITO = "necesita_credito"
# The lead's yes / no to a requirement ("¿Podrías conseguirlo?") and to "nothing fits".
PUEDE_CUMPLIR = "puede_cumplir"
VER_ALTERNATIVAS = "ver_alternativas"
# Requirements the lead said they can meet anyway (LeadConditions.acepta).
ACCEPTED = "acepta_requisitos"

FACTS: Mapping[str, QualificationQuestion] = {
    question.key: question
    for question in (
        QualificationQuestion(
            GARANTIA,
            "Qué garantía tiene para alquilar",
            QuestionKind.CHOICE,
            LEAD_GUARANTEES,
        ),
        QualificationQuestion(
            PLAZO_MESES, "Por cuántos meses quiere alquilar", QuestionKind.NUMBER
        ),
        QualificationQuestion("temporal", "Si busca un alquiler temporario", QuestionKind.BOOLEAN),
        QualificationQuestion("quiere_amueblado", "Si lo quiere amueblado", QuestionKind.BOOLEAN),
        QualificationQuestion("tiene_mascota", "Si tiene mascota", QuestionKind.BOOLEAN),
        QualificationQuestion(
            "uso_profesional", "Si es para uso profesional", QuestionKind.BOOLEAN
        ),
        QualificationQuestion(
            NECESITA_CREDITO, "Si necesita crédito hipotecario", QuestionKind.BOOLEAN
        ),
        QualificationQuestion(
            "necesita_financiacion", "Si necesita financiación del dueño", QuestionKind.BOOLEAN
        ),
        QualificationQuestion(
            "ofrece_permuta", "Si ofrece una propiedad en permuta", QuestionKind.BOOLEAN
        ),
    )
}
RENT_FACTS = (
    GARANTIA,
    PLAZO_MESES,
    "temporal",
    "quiere_amueblado",
    "tiene_mascota",
    "uso_profesional",
)
SALE_FACTS = (
    NECESITA_CREDITO,
    "necesita_financiacion",
    "ofrece_permuta",
    "tiene_mascota",
    "uso_profesional",
)
# Asked (not only captured) before a visit, when the chosen property needs them.
ACTIVE_QUESTIONS = (GARANTIA, PLAZO_MESES, NECESITA_CREDITO)
CONDITION_KEYS = frozenset(FACTS)

CONFIRMATIONS: Mapping[str, QualificationQuestion] = {
    PUEDE_CUMPLIR: QualificationQuestion(
        PUEDE_CUMPLIR, "Si puede cumplir ese requisito", QuestionKind.BOOLEAN
    ),
    VER_ALTERNATIVAS: QualificationQuestion(
        VER_ALTERNATIVAS,
        "Si le interesa ver propiedades con esa condición",
        QuestionKind.BOOLEAN,
    ),
}


# Short answers to a yes / no question, read without the model: a whole message made only of
# these ("si dale", "ok, lo consigo") is a yes; one of the "no" answers is a no.
_YES_PHRASES = (
    "lo consigo",
    "de una",
    "por supuesto",
    "si",
    "dale",
    "ok",
    "okay",
    "claro",
    "puedo",
    "obvio",
    "bueno",
)
_NO_ANSWERS = frozenset({"no", "no puedo", "no tengo", "no lo consigo", "no podria", "nop"})


def read_yes_no(text: str) -> bool | None:
    """The lead's yes or no when the message is one of the common short answers; None
    otherwise (it is left to the model: "no sé" is neither)."""
    said = " ".join(re.findall(r"[a-z]+", normalize(text)))
    if said in _NO_ANSWERS:
        return False
    rest = said
    while rest:
        phrase = next((p for p in _YES_PHRASES if rest == p or rest.startswith(p + " ")), None)
        if phrase is None:
            return None
        rest = rest[len(phrase) :].strip()
    return True if said else None


def facts_for(operation: Operation | None) -> list[QualificationQuestion]:
    """The facts that apply to the operation (all of them while it is unknown)."""
    if operation is Operation.RENT:
        keys: Sequence[str] = RENT_FACTS
    elif operation is Operation.SALE:
        keys = SALE_FACTS
    else:
        keys = tuple(FACTS)
    return [FACTS[key] for key in keys]


def lead_conditions(answers: Mapping[str, Any]) -> LeadConditions:
    return LeadConditions.from_answers(answers)


def gate_question(
    conditions: PropertyConditions,
    operation: Operation | None,
    answers: Mapping[str, Any],
    enabled: set[str],
    asked: Sequence[str] = (),
) -> QualificationQuestion | None:
    """The one decisive question the chosen property needs and the lead has not answered
    (never one already asked about this property)."""
    lead = lead_conditions(answers)
    wanted: list[str] = []
    if operation is Operation.RENT:
        if conditions.garantias is not None and lead.garantia is None:
            wanted.append(GARANTIA)
        term_matters = conditions.contrato_minimo_meses is not None or conditions.temporal is False
        if term_matters and lead.plazo_meses is None and lead.temporal is None:
            wanted.append(PLAZO_MESES)
    elif operation is Operation.SALE:
        if conditions.apto_credito is not None and lead.necesita_credito is None:
            wanted.append(NECESITA_CREDITO)
    for key in wanted:
        if key in enabled and key not in asked:
            return FACTS[key]
    return None


FACT_VALUE_LABELS: Mapping[str, str] = {
    "propietaria": "Garantía propietaria",
    "caucion": "Seguro de caución",
    "recibo_de_sueldo": "Recibo de sueldo",
    "ninguna": "No tiene garantía",
    "otra": "Otra garantía",
}


def fact_value(key: str, value: Any) -> str | None:
    """How the inbox shows a fact."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if key == GARANTIA:
        return FACT_VALUE_LABELS.get(str(value), str(value))
    if key == PLAZO_MESES and isinstance(value, int):
        return "1 mes" if value == 1 else f"{value} meses"
    return str(value)
