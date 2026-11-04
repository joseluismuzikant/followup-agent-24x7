"""Backoffice Consumo: LLM cost, conversations and templates per business and UTC month, and
the monthly cost alert."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from followup_core.notifications.infrastructure.smtp import RecordingEmailSender
from followup_core.scheduling.domain.jobs import Job, JobStatus
from followup_core.scheduling.infrastructure.queue import SqlAlchemyJobQueue
from followup_core.tenancy.infrastructure.audit_repository import SqlAlchemyAuditLog
from inmo24x7_api.billing.application.cost_alert import COST_ALERT_JOB, CheckCostAlerts
from inmo24x7_api.billing.domain.usage import Month
from inmo24x7_api.billing.infrastructure.queries import SqlAlchemyUsageQueries
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from test_setup_endpoints import Account

NOVEMBER = datetime(2026, 11, 15, 12, tzinfo=UTC)


class Usage:
    def __init__(self, client: TestClient, auth, database) -> None:
        self.sessions = sessionmaker(bind=database)
        self.sur = Account(client, auth, "Inmobiliaria Sur")
        self.norte = Account(client, auth, "Inmobiliaria Norte")
        self.admin = Account(client, auth, "Plataforma")
        auth.make_admin(self.admin.user_id)
        self.client = client

    def get(self, path: str):
        return self.client.get(path, headers=self.admin.headers)

    def execute(self, statement: str, **params: object) -> None:
        with self.sessions() as session:
            session.execute(text(statement), params)
            session.commit()

    def call(
        self,
        tenant_id: UUID,
        at: datetime,
        cost: str | None,
        *,
        is_test: bool = False,
        operation: str = "compose_reply",
        model: str = "anthropic:claude-test",
        tokens: tuple[int, int] = (1_000, 100),
        reported: bool = True,
    ) -> None:
        self.execute(
            """
            INSERT INTO llm_usage (id, tenant_id, thread_id, channel, is_test, operation,
              provider, model, input_tokens, output_tokens, cached_input_tokens,
              usage_reported, latency_ms, succeeded, cost_usd, price_version, created_at)
            VALUES (:id, :tenant, :thread, :channel, :test, :operation, 'anthropic', :model,
              :input, :output, 0, :reported, 900, true, :cost, NULL, :at)
            """,
            id=uuid4(),
            tenant=tenant_id,
            thread=uuid4(),
            channel="simulator" if is_test else "whatsapp",
            test=is_test,
            operation=operation,
            model=model,
            input=tokens[0],
            output=tokens[1],
            reported=reported,
            cost=Decimal(cost) if cost is not None else None,
            at=at,
        )

    def thread(self, tenant_id: UUID, channel: str = "whatsapp") -> UUID:
        thread_id = uuid4()
        self.execute(
            """
            INSERT INTO conversation_threads (id, key, tenant_id, channel, visitor_id,
              agent_config_version, status, control, created_at)
            VALUES (:id, :key, :tenant, :channel, :visitor, 1, 'open', 'agent', :at)
            """,
            id=thread_id,
            key=f"{tenant_id}:{channel}:{thread_id}",
            tenant=tenant_id,
            channel=channel,
            visitor=str(thread_id),
            at=NOVEMBER - timedelta(days=60),
        )
        return thread_id

    def message(self, thread_id: UUID, at: datetime, direction: str = "inbound") -> UUID:
        message_id = uuid4()
        self.execute(
            """
            INSERT INTO conversation_messages (id, thread_id, direction, author, text,
              content_type, created_at)
            VALUES (:id, :thread, :direction, :author, 'x', 'text', :at)
            """,
            id=message_id,
            thread=thread_id,
            direction=direction,
            author="visitor" if direction == "inbound" else "agent",
            at=at,
        )
        return message_id

    def template(self, thread_id: UUID, sent_at: datetime | None, kind: str = "template") -> None:
        message_id = self.message(thread_id, sent_at or NOVEMBER, "outbound")
        self.execute(
            """
            INSERT INTO whatsapp_outbound (id, message_id, part, wa_id, body, wamid, status,
              sent_at, updated_at)
            VALUES (:id, :message, 0, '5491100000000', CAST(:body AS jsonb), :wamid, :status,
              :sent_at, :at)
            """,
            id=uuid4(),
            message=message_id,
            body=json.dumps({"type": kind}),
            wamid=f"wamid.{uuid4().hex}" if sent_at else None,
            status="sent" if sent_at else "failed",
            sent_at=sent_at,
            at=NOVEMBER,
        )


@pytest.fixture
def usage(client: TestClient, auth, database) -> Usage:
    return Usage(client, auth, database)


def _row(body: dict, name: str) -> dict:
    return next(row for row in body["businesses"] if row["name"] == name)


def test_consumo_is_for_platform_admins_only(usage: Usage) -> None:
    assert usage.sur.get("/admin/usage").status_code == 403
    assert usage.sur.get("/admin/usage/export.csv").status_code == 403
    assert usage.sur.get(f"/admin/usage/{usage.sur.tenant_id}").status_code == 403


def test_totals_and_one_row_per_business_sorted_by_cost(usage: Usage) -> None:
    sur, norte = usage.sur.tenant_id, usage.norte.tenant_id
    usage.call(sur, NOVEMBER, "0.30")
    usage.call(sur, NOVEMBER, "0.10", is_test=True)
    usage.call(sur, NOVEMBER, None, model="openai:unpriced")
    usage.call(norte, NOVEMBER, "1.00", reported=False, tokens=(0, 0))
    # Two conversations of Sur this month (one in the simulator), each counted once.
    whatsapp = usage.thread(sur)
    usage.message(whatsapp, NOVEMBER)
    usage.message(whatsapp, NOVEMBER + timedelta(hours=1))
    usage.message(usage.thread(sur, "simulator"), NOVEMBER)
    # Templates Meta accepted (a failed one and a free-form message do not count).
    usage.template(whatsapp, NOVEMBER)
    usage.template(whatsapp, NOVEMBER)
    usage.template(whatsapp, None)
    usage.template(whatsapp, NOVEMBER, kind="text")

    body = usage.get("/admin/usage?month=2026-11").json()

    assert body["month"] == "2026-11"
    assert [row["name"] for row in body["businesses"]] == [
        "Inmobiliaria Norte",
        "Inmobiliaria Sur",
    ]
    row = _row(body, "Inmobiliaria Sur")
    assert row["plan"] == "trial"
    assert row["figures"] == {
        "llm_calls": 3,
        "input_tokens": 3_000,
        "output_tokens": 300,
        "cost_usd": "0.400000",
        "cost_per_conversation_usd": "0.200000",
        "test_share": pytest.approx(0.25),
        "conversations": 2,
        "template_messages": 2,
        "unpriced_calls": 1,
        "unreported_calls": 0,
    }
    norte_row = _row(body, "Inmobiliaria Norte")["figures"]
    assert (norte_row["unreported_calls"], norte_row["cost_per_conversation_usd"]) == (1, None)
    totals = body["totals"]
    assert (totals["cost_usd"], totals["llm_calls"], totals["conversations"]) == (
        "1.400000",
        4,
        2,
    )
    assert totals["test_share"] == pytest.approx(0.1 / 1.4)
    # The admin's own tenant is not a business.
    assert "Plataforma" not in {row["name"] for row in body["businesses"]}


def test_months_are_utc_and_half_open(usage: Usage) -> None:
    sur = usage.sur.tenant_id
    last_second = datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC)
    usage.call(sur, last_second, "1.00")
    usage.call(sur, datetime(2026, 12, 1, tzinfo=UTC), "2.00")
    # 21:30 in Buenos Aires on November 30th is already December in UTC.
    usage.call(sur, datetime(2026, 12, 1, 0, 30, tzinfo=UTC), "4.00")

    november = _row(usage.get("/admin/usage?month=2026-11").json(), "Inmobiliaria Sur")
    december = _row(usage.get("/admin/usage?month=2026-12").json(), "Inmobiliaria Sur")

    assert november["figures"]["cost_usd"] == "1.000000"
    assert december["figures"]["cost_usd"] == "6.000000"
    assert usage.get("/admin/usage?month=2026-13").status_code == 422


def test_one_business_daily_detail_and_splits(usage: Usage) -> None:
    sur = usage.sur.tenant_id
    usage.call(sur, datetime(2026, 11, 3, 10, tzinfo=UTC), "0.20", operation="extract")
    usage.call(sur, datetime(2026, 11, 3, 23, 59, tzinfo=UTC), "0.30")
    usage.call(sur, datetime(2026, 11, 20, tzinfo=UTC), None, model="openai:unpriced")
    usage.message(usage.thread(sur), datetime(2026, 11, 3, 9, tzinfo=UTC))

    body = usage.get(f"/admin/usage/{sur}?month=2026-11").json()

    assert body["business"]["name"] == "Inmobiliaria Sur"
    assert len(body["daily"]) == 30
    third = body["daily"][2]
    assert third == {"day": "2026-11-03", "cost_usd": "0.500000", "conversations": 1}
    assert body["daily"][3] == {"day": "2026-11-04", "cost_usd": "0.000000", "conversations": 0}
    assert [(s["key"], s["llm_calls"], s["cost_usd"]) for s in body["by_operation"]] == [
        ("compose_reply", 2, "0.300000"),
        ("extract", 1, "0.200000"),
    ]
    assert [(s["key"], s["unpriced_calls"]) for s in body["by_model"]] == [
        ("anthropic:claude-test", 0),
        ("openai:unpriced", 1),
    ]
    assert usage.get(f"/admin/usage/{uuid4()}").status_code == 404


def test_csv_export_has_the_table(usage: Usage) -> None:
    usage.call(usage.sur.tenant_id, NOVEMBER, "0.40")
    usage.message(usage.thread(usage.sur.tenant_id), NOVEMBER)

    response = usage.get("/admin/usage/export.csv?month=2026-11")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="consumo-2026-11.csv"' in response.headers["content-disposition"]
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Negocio;Plan;Conversaciones;Llamadas al LLM")
    assert lines[1] == "Inmobiliaria Sur;trial;1;1;1000;100;0,4000;0,4000;0,0;0;0"
    assert lines[2].startswith("Inmobiliaria Norte;trial;0;0;")


def test_the_default_month_is_the_current_utc_month(usage: Usage) -> None:
    body = usage.get("/admin/usage").json()

    assert body["month"] == f"{datetime.now(UTC):%Y-%m}"


# --- cost alert ---------------------------------------------------------------------------------


def _alerts(session: Session, limit: Decimal | None, emails: RecordingEmailSender, now: datetime):
    return CheckCostAlerts(
        SqlAlchemyUsageQueries(session),
        SqlAlchemyAuditLog(session),
        emails,
        "soporte@inmo24x7.test",
        limit,
        SqlAlchemyJobQueue(session),
        lambda: now,
    )


def _job() -> Job:
    return Job(uuid4(), COST_ALERT_JOB, {}, NOVEMBER, JobStatus.RUNNING, 1, 3)


def test_the_cost_alert_fires_once_per_business_and_month(usage: Usage) -> None:
    usage.call(usage.sur.tenant_id, NOVEMBER - timedelta(days=1), "30.00")
    usage.call(usage.sur.tenant_id, NOVEMBER, "25.00")
    usage.call(usage.norte.tenant_id, NOVEMBER, "10.00")
    emails = RecordingEmailSender()

    for _ in range(2):
        with usage.sessions() as session:
            _alerts(session, Decimal(50), emails, NOVEMBER)(_job())
            session.commit()

    assert len(emails.sent) == 1
    sent = emails.sent[0]
    assert sent.to == ["soporte@inmo24x7.test"]
    assert "Inmobiliaria Sur" in sent.subject
    assert "USD 55.00" in sent.text and "2026-11" in sent.text
    with usage.sessions() as session:
        events = session.execute(
            text("SELECT tenant_id, details FROM audit_events WHERE action = 'llm_cost_alert'")
        ).all()
        next_runs = session.scalar(
            text("SELECT count(*) FROM jobs WHERE kind = :kind"), {"kind": COST_ALERT_JOB}
        )
    assert [(row.tenant_id, row.details) for row in events] == [
        (usage.sur.tenant_id, {"month": "2026-11", "cost_usd": "55.00"})
    ]
    # Each run schedules tomorrow's (one per day).
    assert next_runs == 1

    # A new month alerts again.
    december = datetime(2026, 12, 2, tzinfo=UTC)
    usage.call(usage.sur.tenant_id, december, "60.00")
    with usage.sessions() as session:
        _alerts(session, Decimal(50), emails, december)(_job())
        session.commit()
    assert len(emails.sent) == 2


def test_the_cost_alert_is_off_without_a_limit(usage: Usage) -> None:
    usage.call(usage.sur.tenant_id, NOVEMBER, "999.00")
    emails = RecordingEmailSender()

    with usage.sessions() as session:
        _alerts(session, None, emails, NOVEMBER)(_job())
        session.commit()

    assert emails.sent == []


def test_month_bounds() -> None:
    assert Month.parse("2026-12").end == datetime(2027, 1, 1, tzinfo=UTC)
    assert str(Month.of(datetime(2026, 11, 30, 23, 0, tzinfo=UTC))) == "2026-11"
