"""Fake Tokko Broker and a fake webhook receiver behind httpx.MockTransport: nothing leaves
the machine. The Tokko shapes follow integrations/tokko.py (see "to verify with a real key"
in docs/integrations.md)."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from inmo24x7_api.container import get_integration_clients
from inmo24x7_api.integrations import wiring as integration_wiring
from inmo24x7_api.integrations.tokko import TokkoClient
from inmo24x7_api.integrations.webhook import WebhookClient
from inmo24x7_api.main import app

TOKKO_KEY = "tokko-key-0123456789"
TOKKO_BASE = "https://tokko.test/api/v1"
WEBHOOK_URL = "https://crm.example.com/hooks/inmo"


def tokko_property(
    tokko_id: int,
    *,
    title: str = "2 ambientes luminoso",
    address: str = "Gorriti 4800",
    zone: str = "Palermo",
    rooms: int | None = 2,
    operations: list[dict[str, Any]] | None = None,
    link: str | None = None,
    reference: str | None = None,
) -> dict[str, Any]:
    return {
        "id": tokko_id,
        "reference_code": reference or f"TKO{tokko_id}",
        "publication_title": title,
        "address": address,
        "fake_address": "",
        "location": {"name": zone, "full_location": f"Argentina | Capital Federal | {zone}"},
        "room_amount": rooms,
        "suite_amount": 1,
        "public_url": link or f"https://www.inmosur.com.ar/propiedad/{tokko_id}",
        "operations": operations
        if operations is not None
        else [
            {
                "operation_type": "Alquiler",
                "operation_id": 2,
                "prices": [{"currency": "ARS", "price": 850000, "period": 0}],
            }
        ],
    }


def sale(price: int = 185000) -> dict[str, Any]:
    return {
        "operation_type": "Venta",
        "operation_id": 1,
        "prices": [{"currency": "USD", "price": price, "period": 0}],
    }


def rent(price: int = 850000) -> dict[str, Any]:
    return {
        "operation_type": "Alquiler",
        "operation_id": 2,
        "prices": [{"currency": "ARS", "price": price, "period": 0}],
    }


class FakeTokko:
    def __init__(self, page_size: int = 2) -> None:
        self.properties: list[dict[str, Any]] = []
        self.contacts: list[dict[str, Any]] = []
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.page_size = page_size
        # Status codes to answer the next web contacts with (then 201).
        self.contact_failures: list[int] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.requests.append((request.method, request.url.path, params))
        if self.down:
            return httpx.Response(503)
        if params.get("key") != TOKKO_KEY:
            return httpx.Response(401, json={"error": "Unauthorized"})
        assert params.get("format") == "json" and params.get("lang") == "es_ar"
        if request.method == "GET" and request.url.path == "/api/v1/property/":
            limit = min(int(params.get("limit", 20)), self.page_size)
            offset = int(params.get("offset", 0))
            objects = self.properties[offset : offset + limit]
            more = offset + limit < len(self.properties)
            return httpx.Response(
                200,
                json={
                    "meta": {
                        "limit": limit,
                        "offset": offset,
                        "total_count": len(self.properties),
                        "next": f"/api/v1/property/?offset={offset + limit}" if more else None,
                        "previous": None,
                    },
                    "objects": objects,
                },
            )
        if request.method == "POST" and request.url.path == "/api/v1/webcontact/":
            if self.contact_failures:
                return httpx.Response(self.contact_failures.pop(0))
            body = json.loads(request.content)
            self.contacts.append(body)
            return httpx.Response(201, json={"id": 9000 + len(self.contacts)})
        return httpx.Response(404)


class FakeReceiver:
    def __init__(self) -> None:
        self.received: list[httpx.Request] = []
        self.statuses: list[int] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.received.append(request)
        return httpx.Response(self.statuses.pop(0) if self.statuses else 200)

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(item.content) for item in self.received]


@contextmanager
def fake_integrations(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[FakeTokko, FakeReceiver]]:
    tokko = FakeTokko()
    receiver = FakeReceiver()
    clients = integration_wiring.IntegrationClients(
        tokko=TokkoClient(TOKKO_BASE, transport=httpx.MockTransport(tokko.handler)),
        webhook=WebhookClient(transport=httpx.MockTransport(receiver.handler)),
    )
    monkeypatch.setattr(integration_wiring, "get_clients", lambda: clients)
    app.dependency_overrides[get_integration_clients] = lambda: clients
    try:
        yield tokko, receiver
    finally:
        app.dependency_overrides.pop(get_integration_clients, None)
