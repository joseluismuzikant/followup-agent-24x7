from fastapi.testclient import TestClient
from inmo24x7_api.main import settings as app_settings
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_propagates_request_id(client: TestClient) -> None:
    response = client.get("/health")

    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    assert int(request_id, 16) >= 0


def test_readiness_checks_the_database(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
        "version": app_settings.version,
        "commit": app_settings.commit,
        "build_date": app_settings.build_date,
    }


def test_readiness_returns_503_when_database_is_unavailable(
    client: TestClient,
    monkeypatch,
) -> None:
    def fail_execute(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("database unavailable"))

    monkeypatch.setattr(Session, "execute", fail_execute)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"code": "database_unavailable"}


def test_unknown_route_returns_an_error_code(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"code": "not_found"}
