""" "BAJA" detection: the clear phrases in any case, accent or punctuation, and never "baja"
with another meaning (those are left to the model's `wants_opt_out`)."""

import pytest
from followup_core.messaging.domain.opt_out import is_opt_out


@pytest.mark.parametrize(
    "text",
    [
        "BAJA",
        "baja",
        "Baja.",
        "BAJA!!!",
        "baja por favor",
        "Baja, gracias",
        "STOP",
        "stop",
        "No me escriban más",
        "no me escriban mas!!",
        "NO ME ESCRIBAN MÁS.",
        "Por favor no me escriban nunca más",
        "No quiero que me contacten",
        "no quiero que me contacten más, gracias",
        "Dejen de escribirme",
        "dejen de escribirme por favor",
        "No me contacten más",
        "Quiero darme de baja",
        "denme de baja",
        "No quiero recibir más mensajes",
    ],
)
def test_clear_opt_outs(text: str) -> None:
    assert is_opt_out(text)


@pytest.mark.parametrize(
    "text",
    [
        "¿La planta baja está disponible?",
        "¿Baja el precio?",
        "busco una planta baja con patio",
        "baja a 800 mil?",
        "La de Baja California",
        "Hola, busco alquilar en Palermo",
        "no me escribieron todavía",
        "stop motion",
        "",
        "   ",
        "!!!",
    ],
)
def test_baja_with_another_meaning_is_not_an_opt_out(text: str) -> None:
    assert not is_opt_out(text)
