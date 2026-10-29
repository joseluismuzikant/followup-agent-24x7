import pytest
from followup_core.conversation.domain.answers import parse_answer
from followup_core.tenancy.domain.agent_config import QualificationQuestion, QuestionKind


def _question(kind: QuestionKind, options: tuple[str, ...] = ()) -> QualificationQuestion:
    return QualificationQuestion("q", "Pregunta", kind, options)


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [
        (QuestionKind.CHOICE, "ALQUILER", "alquiler"),
        (QuestionKind.CHOICE, "permuta", None),
        (QuestionKind.CHOICE, 3, None),
        (QuestionKind.TEXT, "  Villa   Urquiza ", "Villa Urquiza"),
        (QuestionKind.TEXT, "", None),
        (QuestionKind.NUMBER, 3, 3),
        (QuestionKind.NUMBER, "3 ambientes", 3),
        (QuestionKind.NUMBER, True, None),
        (QuestionKind.NUMBER, 5000, None),
        (
            QuestionKind.MONEY,
            {"amount": "120.000", "currency": "usd"},
            {"amount": 120000, "currency": "USD"},
        ),
        (QuestionKind.MONEY, {"amount": 900000, "currency": "EUR"}, None),
        (QuestionKind.MONEY, 900000, None),
        (QuestionKind.BOOLEAN, True, True),
        (QuestionKind.BOOLEAN, "sí", None),
    ],
)
def test_answers_are_validated_against_the_question_kind(kind, raw, expected) -> None:
    question = _question(kind, ("compra", "alquiler") if kind is QuestionKind.CHOICE else ())

    assert parse_answer(question, raw) == expected
