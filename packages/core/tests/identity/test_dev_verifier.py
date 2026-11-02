import pytest
from followup_core.identity.domain.errors import InvalidTokenError
from followup_core.identity.infrastructure.dev_verifier import DevTokenVerifier, dev_user_id


def test_accepts_dev_tokens_and_maps_the_email_to_a_stable_user() -> None:
    verifier = DevTokenVerifier()

    first = verifier.verify("dev:Dueno@InmobiliariaSur.test")
    second = verifier.verify("dev:dueno@inmobiliariasur.test")

    assert first.email == "dueno@inmobiliariasur.test"
    assert first.user_id == second.user_id == dev_user_id("dueno@inmobiliariasur.test")
    assert verifier.verify("dev:otro@local.test").user_id != first.user_id


@pytest.mark.parametrize(
    "token",
    [
        "",
        "dev:",
        "dev:no-es-un-email",
        "eyJhbGciOiJIUzI1NiJ9.e30.x",
        "admin@local.test",
        "Dev:a@b.co",
    ],
)
def test_rejects_anything_else(token: str) -> None:
    with pytest.raises(InvalidTokenError):
        DevTokenVerifier().verify(token)
