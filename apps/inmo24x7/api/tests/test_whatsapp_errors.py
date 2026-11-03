"""Every Meta code we map has a stable internal code, a kind, and Spanish copy for the
inmobiliaria (what happened and what to do) plus a technical line for admins."""

import pytest
from followup_core.messaging.application.health import stops_sending
from followup_core.messaging.domain.meta_errors import (
    INTERNAL,
    MetaErrorKind,
    classify,
    mapped_codes,
)
from inmo24x7_api.whatsapp_errors import COPY, GENERIC, translate


@pytest.mark.parametrize("meta_code", mapped_codes())
def test_each_mapped_code_has_a_kind_and_its_own_copy(meta_code: str) -> None:
    error = classify(meta_code)
    translated = translate(meta_code)

    assert error.code != "unknown"
    assert error.code in COPY
    assert translated.meta_code == meta_code
    for text in (translated.title, translated.message, translated.action, translated.admin_detail):
        assert text.strip() and text == text.strip()


@pytest.mark.parametrize("code", sorted(INTERNAL))
def test_the_platforms_own_codes_are_translated(code: str) -> None:
    assert translate(code).code == code
    assert translate(code).title != GENERIC.title


def test_the_screens_examples_say_exactly_what_the_spec_says() -> None:
    taken = translate("2388012")
    revoked = translate("190")

    assert taken.message == (
        "Ese número ya está registrado en otra cuenta. Eliminalo de la app de WhatsApp o "
        "elegí otro número, y volvé a intentar."
    )
    assert revoked.title == "El permiso de Meta venció"
    assert revoked.admin_detail == "El cliente quitó el acceso de la app en su cuenta de Meta."


@pytest.mark.parametrize("meta_code", ["299", "250", "200"])
def test_the_permission_range_is_an_auth_error(meta_code: str) -> None:
    assert classify(meta_code).kind is MetaErrorKind.AUTH
    assert stops_sending(meta_code)


@pytest.mark.parametrize("meta_code", ["999999", "", None, "abc"])
def test_unknown_codes_get_the_generic_copy_and_never_stop_sending(meta_code) -> None:
    translated = translate(meta_code)

    assert translated.code == "unknown"
    assert (translated.title, translated.message) == (GENERIC.title, GENERIC.message)
    assert not stops_sending(meta_code or "")


@pytest.mark.parametrize(
    ("meta_code", "stops"),
    [
        ("190", True),
        ("0", True),
        ("10", True),
        ("131031", True),
        ("app_removed", True),
        ("account_disabled", True),
        ("131026", False),  # one recipient
        ("131047", False),  # one conversation's window
        ("130429", False),  # throttling: retried
        ("132001", False),  # a template
    ],
)
def test_only_auth_and_account_errors_stop_sending(meta_code: str, stops: bool) -> None:
    assert stops_sending(meta_code) is stops
