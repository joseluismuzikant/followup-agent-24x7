"""A Cuentas Claras WhatsApp harness: the Graph API mocked at the HTTP level (messages and
the WABA's message templates), a recording email sender, signed webhooks from
scripts/simulate_whatsapp.py, and a worker whose clock the test controls. Nothing reaches
Meta."""

import json
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from conftest import Owner, make_admin
from cuentas_claras_api.config import get_settings
from cuentas_claras_api.container import get_clock, get_messaging_services
from cuentas_claras_api.main import app
from cuentas_claras_api.worker import job_handlers
from fastapi.testclient import TestClient
from followup_core.messaging.infrastructure.crypto import TokenCipher
from followup_core.messaging.infrastructure.graph import GraphClient
from followup_core.notifications.infrastructure.smtp import RecordingEmailSender
from followup_core.scheduling.infrastructure.queue import JobRunner
from followup_core.tenancy.domain.product import Product
from followup_platform.whatsapp.wiring import MessagingServices
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))

import simulate_whatsapp  # noqa: E402

APP_SECRET = "cc-test-app-secret"
VERIFY_TOKEN = "cc-test-verify-token"
PHONE_NUMBER_ID = "pn-cc-1"
WABA_ID = "waba-cc-1"
CLIENT_WA_ID = "5491155550301"
# Argentine mobiles go to the Cloud API's `to` without the 9.
CLIENT_TO = "541155550301"
PANEL = "https://cuentasclaras.example.com"
BA = ZoneInfo("America/Argentina/Buenos_Aires")
# Monday 16 November 2026, 10:00 in Buenos Aires: inside the default window (9–12).
MONDAY = date(2026, 11, 16)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), BA).astimezone(UTC)


class FakeGraph:
    """Answers like the Graph API and records every request. `fail_next` queues error
    responses (status, Meta code) for the next message sends; templates are created as
    PENDING and listed with `listed_status` (Meta's review)."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.fail_next: list[tuple[int, int]] = []
        self.templates: dict[str, dict[str, Any]] = {}
        self._sent = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        path = request.url.path
        self.requests.append((request.method, path, body))
        if path.endswith("/message_templates") and request.method == "POST":
            template_id = f"tpl-{len(self.templates) + 1}"
            self.templates[template_id] = {
                "id": template_id,
                "name": body["name"],
                "language": body["language"],
                "status": "PENDING",
                "category": body["category"],
            }
            return httpx.Response(200, json={"id": template_id, "status": "PENDING"})
        if path.endswith("/message_templates"):
            return httpx.Response(200, json={"data": list(self.templates.values())})
        if path.endswith("/messages") and body.get("status") == "read":
            return httpx.Response(200, json={"success": True})
        if path.endswith("/messages"):
            if self.fail_next:
                status, code = self.fail_next.pop(0)
                return httpx.Response(status, json={"error": {"code": code, "message": "x"}})
            self._sent += 1
            return httpx.Response(200, json={"messages": [{"id": f"wamid.cc.{self._sent}"}]})
        if path.endswith("/subscribed_apps"):
            return httpx.Response(200, json={"success": True})
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"display_phone_number": "+54 9 11 5555-0100", "verified_name": "Delta"},
            )
        return httpx.Response(404, json={"error": {"code": 100}})

    def review(self, status: str, reason: str | None = None) -> None:
        """Meta reviewed every template (what the next sync reads)."""
        for template in self.templates.values():
            template["status"] = status
            template["rejected_reason"] = reason or "NONE"

    def sent(self) -> list[dict[str, Any]]:
        return [
            body
            for method, path, body in self.requests
            if method == "POST" and path.endswith("/messages") and "status" not in body
        ]


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


def build_services(graph: FakeGraph) -> MessagingServices:
    settings = replace(
        get_settings(),
        meta_app_secret=APP_SECRET,
        whatsapp_verify_token=VERIFY_TOKEN,
        whatsapp_sender="cloud",
        inbound_debounce_seconds=1.0,
        panel_url=PANEL,
    )
    return MessagingServices(
        settings=settings,
        cipher=TokenCipher.from_setting(settings.token_encryption_key),
        graph=GraphClient(transport=httpx.MockTransport(graph.handler)),
        email=RecordingEmailSender(),
    )


class World:
    """One business (its owner), a platform admin, a Cuentas Claras number and the worker."""

    def __init__(
        self, client: TestClient, sessions: sessionmaker[Session], now: datetime | None = None
    ) -> None:
        self.client = client
        self.sessions = sessions
        self.graph = FakeGraph()
        self.services = build_services(self.graph)
        self.clock = Clock(now or at(MONDAY, 10))
        app.dependency_overrides[get_messaging_services] = lambda: self.services
        app.dependency_overrides[get_clock] = lambda: self.clock
        self.owner = Owner(client)
        self.admin = Owner(client, name="Plataforma")
        make_admin(sessions, self.admin.profile_id)
        self._number = 1200
        self.runner = JobRunner(
            sessions,
            lambda session: job_handlers(session, services=self.services, clock=self.clock),
            self.clock,
            jitter=lambda: 0.5,
            queue=Product.CUENTAS_CLARAS,
        )

    @property
    def emails(self) -> RecordingEmailSender:
        assert isinstance(self.services.email, RecordingEmailSender)
        return self.services.email

    def connect(self, **extra: Any):  # noqa: ANN201 - the test client's response
        body = {
            "phone_number_id": PHONE_NUMBER_ID,
            "waba_id": WABA_ID,
            "display_phone_number": "+54 9 11 5555-0100",
            "access_token": "EAAG-cc-secret-token",
            "sender": "cloud",
            **extra,
        }
        return self.admin.client.put(
            f"/admin/tenants/{self.owner.tenant_id}/whatsapp", json=body, headers=self.admin.headers
        )

    def run(self) -> int:
        return self.runner.run_due()

    def ready(self) -> None:
        """Connected, templates submitted and approved by Meta (through its webhook)."""
        assert self.connect().status_code == 200
        self.run()
        for template_id in list(self.graph.templates):
            assert self.template_status(template_id, "APPROVED") == 200

    def post(self, payload: dict[str, Any], secret: str = APP_SECRET) -> int:
        body = simulate_whatsapp.encode(payload)
        return self.client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": simulate_whatsapp.sign(body, secret),
            },
        ).status_code

    def template_status(self, template_id: str, event: str, reason: str | None = None) -> int:
        return self.post(
            simulate_whatsapp.template_status_payload(
                template_id, event, reason=reason, waba_id=WABA_ID
            )
        )

    def reply(self, text: str, sender: str = CLIENT_WA_ID) -> int:
        return self.post(
            simulate_whatsapp.message_payload(text, sender=sender, phone_number_id=PHONE_NUMBER_ID)
        )

    def client_with_invoices(
        self, *due_dates: date, whatsapp: str = "+54 9 11 5555-0301", name: str = "Edificio Güemes"
    ) -> tuple[UUID, list[UUID]]:
        response = self.owner.post(
            "/clients",
            {"name": name, "whatsapp": whatsapp, "cuit": "", "email": "pagos@guemes.test"},
        )
        assert response.status_code == 201, response.json()
        client_id = UUID(response.json()["id"])
        invoices = []
        for due in due_dates:
            self._number += 1
            created = self.owner.post(
                "/invoices",
                {
                    "client_id": str(client_id),
                    "invoice_type": "B",
                    "point_of_sale": 3,
                    "number": self._number,
                    "issue_date": (due - timedelta(days=30)).isoformat(),
                    "due_date": due.isoformat(),
                    "amount": "180000.00",
                },
            )
            assert created.status_code == 201, created.json()
            invoices.append(UUID(created.json()["id"]))
        return client_id, invoices

    def plan(self) -> dict[str, Any]:
        response = self.admin.client.post(
            f"/admin/tenants/{self.owner.tenant_id}/reminders/plan", headers=self.admin.headers
        )
        assert response.status_code == 200, response.json()
        return response.json()

    def sql(self, statement: str, **params: Any) -> list[Any]:
        with self.sessions() as session:
            return list(session.execute(text(statement), params).all())

    def events(self) -> list[tuple[str, str | None]]:
        return [
            (row.outcome, row.reason)
            for row in self.sql(
                "SELECT outcome, reason FROM cc_reminder_events ORDER BY created_at"
            )
        ]

    def reminder_messages(self) -> list[dict[str, Any]]:
        """Template messages sent to the client (not read receipts)."""
        return [body for body in self.graph.sent() if body.get("type") == "template"]
