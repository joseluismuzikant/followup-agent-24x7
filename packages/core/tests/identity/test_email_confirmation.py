"""Supabase Auth's record of the user decides whether an email is confirmed."""

import httpx
import pytest
from followup_core.identity.infrastructure.supabase_email import (
    DevEmailConfirmation,
    SupabaseEmailConfirmation,
)


def confirmation(handler) -> SupabaseEmailConfirmation:
    return SupabaseEmailConfirmation(
        "https://ref.supabase.co/", "anon-key", transport=httpx.MockTransport(handler)
    )


def user(status: int = 200, **body) -> object:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["apikey"] = request.headers.get("apikey")
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(status, json=body)

    handler.seen = seen  # type: ignore[attr-defined]
    return handler


def test_a_confirmed_email_with_the_same_address_is_confirmed() -> None:
    handler = user(email="Ana@Sur.test", email_confirmed_at="2026-11-05T12:00:00Z")

    assert confirmation(handler).is_confirmed("jwt", "ana@sur.test") is True
    assert handler.seen == {  # type: ignore[attr-defined]
        "url": "https://ref.supabase.co/auth/v1/user",
        "apikey": "anon-key",
        "auth": "Bearer jwt",
    }


@pytest.mark.parametrize(
    "handler",
    [
        user(email="ana@sur.test", email_confirmed_at=None),
        user(email="ana@sur.test"),
        user(email="otra@sur.test", email_confirmed_at="2026-11-05T12:00:00Z"),
        user(401, msg="invalid JWT"),
        user(500),
    ],
)
def test_anything_else_is_not_confirmed(handler) -> None:
    assert confirmation(handler).is_confirmed("jwt", "ana@sur.test") is False


def test_supabase_unreachable_is_not_confirmed() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    assert confirmation(down).is_confirmed("jwt", "ana@sur.test") is False


def test_dev_tokens_count_as_confirmed() -> None:
    assert DevEmailConfirmation().is_confirmed("dev:ana@sur.test", "ana@sur.test")
    assert not DevEmailConfirmation().is_confirmed("eyJ...", "ana@sur.test")
