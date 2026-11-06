"""A WhatsApp test harness: the Graph API mocked at the HTTP level (httpx.MockTransport),
a recording email sender, signed webhook posts built by scripts/simulate_whatsapp.py, and a
worker whose clock the test controls."""

import json
import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi.testclient import TestClient
from followup_core.conversation.domain.llm import LanguageModel
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from followup_core.messaging.infrastructure.crypto import TokenCipher
from followup_core.messaging.infrastructure.graph import GraphClient
from followup_core.notifications.infrastructure.smtp import RecordingEmailSender
from followup_core.scheduling.infrastructure.queue import JobRunner
from inmo24x7_api.config import get_settings
from inmo24x7_api.container import MessagingServices, job_handlers
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))

import simulate_whatsapp  # noqa: E402

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"
PHONE_NUMBER_ID = "pn-test-1"
VISITOR = "5491155550188"
# What the Cloud API's `to` carries for VISITOR: Argentine mobiles go without the 9.
VISITOR_TO = "541155550188"


class FakeGraph:
    """Answers like the Graph API and records every request. `fail_next` queues error
    responses (status, Meta code) for the next send calls; `fail_on` queues them for any
    call whose path ends with the key (Embedded Signup steps, the phone number read)."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.fail_next: list[tuple[int, int]] = []
        self.fail_on: dict[str, list[tuple[int, int]]] = {}
        self.verification_status = "verified"
        self.quality_rating = "GREEN"
        self.name_status = "APPROVED"
        self._sent = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.requests.append((request.method, request.url.path, body))
        path = request.url.path
        for suffix, failures in self.fail_on.items():
            if path.endswith(suffix) and failures:
                status, code = failures.pop(0)
                return httpx.Response(status, json={"error": {"code": code, "message": "x"}})
        if path.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "EAAB-business-token"})
        if path.endswith("/register"):
            return httpx.Response(200, json={"success": True})
        if request.method == "GET" and "verification_status" in request.url.params.get(
            "fields", ""
        ):
            return httpx.Response(200, json={"verification_status": self.verification_status})
        if path.endswith("/messages") and body.get("status") == "read":
            return httpx.Response(200, json={"success": True})
        if path.endswith("/messages"):
            if self.fail_next:
                status, code = self.fail_next.pop(0)
                return httpx.Response(status, json={"error": {"code": code, "message": "x"}})
            self._sent += 1
            return httpx.Response(200, json={"messages": [{"id": f"wamid.out.{self._sent}"}]})
        if path.endswith("/subscribed_apps"):
            return httpx.Response(200, json={"success": True})
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "display_phone_number": "+54 9 11 5555-0100",
                    "verified_name": "Inmo Sur",
                    "quality_rating": self.quality_rating,
                    "name_status": self.name_status,
                },
            )
        return httpx.Response(404, json={"error": {"code": 100}})

    @property
    def accepted(self) -> int:
        """Messages Meta accepted (got a wamid); rejected attempts do not count."""
        return self._sent

    def sent(self) -> list[dict[str, Any]]:
        """Bodies of the messages sent (not read receipts)."""
        return [
            body
            for method, path, body in self.requests
            if method == "POST" and path.endswith("/messages") and "status" not in body
        ]


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


def build_services(graph: FakeGraph, debounce: float = 3.0) -> MessagingServices:
    settings = replace(
        get_settings(),
        meta_app_secret=APP_SECRET,
        whatsapp_verify_token=VERIFY_TOKEN,
        whatsapp_sender="cloud",
        inbound_debounce_seconds=debounce,
        panel_url="https://panel.example.com",
        meta_app_id="app-123",
        meta_embedded_signup_config_id="config-456",
    )
    return MessagingServices(
        settings=settings,
        cipher=TokenCipher.from_setting(settings.token_encryption_key),
        graph=GraphClient(transport=httpx.MockTransport(graph.handler)),
        email=RecordingEmailSender(),
    )


class WhatsAppWorld:
    def __init__(
        self,
        client: TestClient,
        sessions: sessionmaker[Session],
        services: MessagingServices,
        graph: FakeGraph,
        llm: LanguageModel | None = None,
    ) -> None:
        self.client = client
        self.sessions = sessions
        self.services = services
        self.graph = graph
        self.clock = Clock()
        self.llm = llm or FakeLanguageModel()
        self.runner = JobRunner(
            sessions,
            lambda session: job_handlers(session, services, self.llm, None, self.clock),
            self.clock,
            jitter=lambda: 0.5,
        )

    @property
    def emails(self) -> RecordingEmailSender:
        assert isinstance(self.services.email, RecordingEmailSender)
        return self.services.email

    def post(self, payload: dict[str, Any], secret: str = APP_SECRET) -> int:
        body = simulate_whatsapp.encode(payload)
        response = self.client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": simulate_whatsapp.sign(body, secret),
            },
        )
        return response.status_code

    def calls(self, suffix: str) -> int:
        return sum(1 for _method, path, _body in self.graph.requests if path.endswith(suffix))

    def say(self, text: str | None, sender: str = VISITOR, **kwargs: Any) -> int:
        return self.post(
            simulate_whatsapp.message_payload(
                text, sender=sender, phone_number_id=PHONE_NUMBER_ID, **kwargs
            )
        )

    def run(self, after_seconds: float = 5) -> int:
        """Lets the debounce pass and runs every due job."""
        self.clock.now = max(self.clock.now, datetime.now(UTC)) + timedelta(seconds=after_seconds)
        return self.runner.run_due()

    def chat(self, *messages: str, sender: str = VISITOR) -> None:
        for message in messages:
            assert self.say(message, sender=sender) == 200
            self.run()

    def sql(self, statement: str, **params: Any) -> list[Any]:
        with self.sessions() as session:
            return list(session.execute(text(statement), params).all())

    def execute(self, statement: str, **params: Any) -> None:
        with self.sessions() as session:
            session.execute(text(statement), params)
            session.commit()

    def jobs(self, kind: str) -> list[tuple[str, int]]:
        return [
            (row.status, row.attempts)
            for row in self.sql("SELECT status, attempts FROM jobs WHERE kind = :k", k=kind)
        ]

    def transcript(self, sender: str = VISITOR) -> list[tuple[str, str, str]]:
        return [
            (row.direction, row.author, row.text)
            for row in self.sql(
                "SELECT m.direction, m.author, m.text FROM conversation_messages m "
                "JOIN conversation_threads t ON t.id = m.thread_id "
                "WHERE t.visitor_id = :v AND t.channel = 'whatsapp' ORDER BY m.seq",
                v=sender,
            )
        ]

    def outbound(self) -> list[tuple[str, str | None, str | None]]:
        return [
            (row.status, row.wamid, row.error_code)
            for row in self.sql(
                "SELECT o.status, o.wamid, o.error_code FROM whatsapp_outbound o "
                "JOIN conversation_messages m ON m.id = o.message_id ORDER BY m.seq, o.part"
            )
        ]


def connect(client: TestClient, admin_headers: dict[str, str], tenant_id: UUID, **extra: Any):
    body = {
        "phone_number_id": PHONE_NUMBER_ID,
        "waba_id": "waba-test-1",
        "display_phone_number": "+54 9 11 5555-0100",
        "access_token": "EAAG-secret-token",
        "sender": "cloud",
        **extra,
    }
    return client.put(f"/admin/tenants/{tenant_id}/whatsapp", json=body, headers=admin_headers)


def make_sessions(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


SessionsFactory = Callable[[], Session]
