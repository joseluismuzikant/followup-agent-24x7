"""Backoffice Errores: open Sentry issues through its API (mocked at the HTTP level)."""

from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from inmo24x7_api.backoffice.infrastructure.sentry_issues import SentryIssuesClient
from inmo24x7_api.container import get_sentry_issues
from inmo24x7_api.main import app
from test_setup_endpoints import Account

PROJECTS = {"api": "inmo24x7-api", "panel": "inmo24x7-panel", "backoffice": "inmo24x7-backoffice"}


def _issue(issue_id: str, last_seen: str, **extra) -> dict:
    return {
        "id": issue_id,
        "title": f"RuntimeError: boom {issue_id}",
        "culprit": "inmo24x7_api.leads.router in get_lead",
        "permalink": f"https://acme.sentry.io/issues/{issue_id}/",
        "firstSeen": "2026-11-01T10:00:00Z",
        "lastSeen": last_seen,
        "count": "12",
        "userCount": 3,
        **extra,
    }


class FakeSentry:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[httpx.Request] = []
        self.issues = {
            "inmo24x7-api": [_issue("1", "2026-11-04T10:00:00Z")],
            "inmo24x7-panel": [_issue("2", "2026-11-04T12:00:00Z")],
            "inmo24x7-backoffice": [],
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "nope"})
        slug = request.url.path.split("/")[-3]
        return httpx.Response(200, json=self.issues[slug])


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def admin(client: TestClient, auth) -> Account:
    account = Account(client, auth, "Plataforma")
    auth.make_admin(account.user_id)
    return account


def _use(client: SentryIssuesClient) -> None:
    app.dependency_overrides[get_sentry_issues] = lambda: client


def _client(sentry: FakeSentry, clock: Clock | None = None, **changes) -> SentryIssuesClient:
    options = {
        "api_url": "https://sentry.io",
        "token": "read-token",
        "org": "acme",
        "projects": PROJECTS,
        **changes,
    }
    return SentryIssuesClient(
        **options, transport=httpx.MockTransport(sentry.handler), clock=clock or Clock()
    )


def test_errors_are_for_platform_admins_only(client: TestClient, auth) -> None:
    owner = Account(client, auth)
    _use(_client(FakeSentry()))

    assert owner.get("/admin/errors").status_code == 403


def test_open_issues_of_every_project_newest_first(admin: Account) -> None:
    sentry = FakeSentry()
    _use(_client(sentry))

    body = admin.get("/admin/errors?period=7d").json()

    assert (body["configured"], body["available"]) == (True, True)
    assert body["sentry_issues_url"] == "https://acme.sentry.io/issues/"
    assert [(i["id"], i["project"], i["count"], i["users"]) for i in body["issues"]] == [
        ("2", "panel", 12, 3),
        ("1", "api", 12, 3),
    ]
    assert body["issues"][0]["permalink"] == "https://acme.sentry.io/issues/2/"
    request = sentry.requests[0]
    assert request.headers["Authorization"] == "Bearer read-token"
    assert request.url.path == "/api/0/projects/acme/inmo24x7-api/issues/"
    assert request.url.params["query"] == "is:unresolved lastSeen:-7d"


def test_filters_by_project_and_tenant(admin: Account) -> None:
    sentry = FakeSentry()
    _use(_client(sentry))
    tenant_id = uuid4()

    body = admin.get(f"/admin/errors?project=api&tenant_id={tenant_id}").json()

    assert [issue["id"] for issue in body["issues"]] == ["1"]
    assert len(sentry.requests) == 1
    assert sentry.requests[0].url.params["query"] == (
        f"is:unresolved lastSeen:-24h tenant_id:{tenant_id}"
    )


def test_answers_are_cached_for_a_minute(admin: Account) -> None:
    sentry, clock = FakeSentry(), Clock()
    _use(_client(sentry, clock))

    admin.get("/admin/errors")
    admin.get("/admin/errors")
    assert len(sentry.requests) == 3  # one per project, once

    clock.now += 61
    admin.get("/admin/errors")
    assert len(sentry.requests) == 6


def test_without_settings_it_says_not_configured(admin: Account) -> None:
    sentry = FakeSentry()
    _use(_client(sentry, token=""))

    body = admin.get("/admin/errors").json()

    assert body == {
        "configured": False,
        "available": False,
        "issues": [],
        "sentry_issues_url": "https://acme.sentry.io/issues/",
    }
    assert sentry.requests == []


@pytest.mark.parametrize("status", [500, 401, 429])
def test_a_failing_sentry_is_unavailable_never_a_500(admin: Account, status: int) -> None:
    _use(_client(FakeSentry(status)))

    response = admin.get("/admin/errors")

    assert response.status_code == 200
    assert (response.json()["configured"], response.json()["available"]) == (True, False)


def test_a_timeout_is_unavailable(admin: Account) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    _use(
        SentryIssuesClient(
            "https://sentry.io", "t", "acme", PROJECTS, transport=httpx.MockTransport(timeout)
        )
    )

    assert admin.get("/admin/errors").json()["available"] is False


def test_system_health_links_monitoring(admin: Account) -> None:
    _use(_client(FakeSentry()))

    links = admin.get("/admin/system").json()["links"]

    # GRAFANA_URL is not set in tests: no Grafana links.
    assert links == {
        "grafana_url": "",
        "loki_datasource": "",
        "sentry_issues_url": "https://acme.sentry.io/issues/",
    }


def test_the_test_error_is_a_real_unhandled_500_for_admins_only(
    client: TestClient, auth, admin: Account
) -> None:
    owner = Account(client, auth)
    assert owner.post("/admin/errors/test", {}).status_code == 403

    with TestClient(app, raise_server_exceptions=False) as raw:
        response = raw.post("/admin/errors/test", headers=admin.headers)

    assert response.status_code == 500
    assert response.json() == {"code": "internal_error"}
    assert response.headers["X-Request-ID"]
