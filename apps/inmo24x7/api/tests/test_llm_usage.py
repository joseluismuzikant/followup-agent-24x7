"""Every LLM call is recorded with its tokens and its cost, even when the turn rolls back."""

import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from followup_core.conversation.domain.llm import (
    Extraction,
    ExtractionRequest,
    Reply,
    ReplyRequest,
    TokenUsage,
)
from followup_core.conversation.domain.usage import (
    LlmCall,
    LlmOperation,
    Price,
    PriceBook,
    cost_usd,
    price_call,
)
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from followup_core.conversation.infrastructure.models import LlmUsageModel
from followup_core.conversation.infrastructure.usage import SqlAlchemyLlmUsageRecorder
from inmo24x7_api.billing.infrastructure.prices import PRICES_FILE, PriceFileError, parse_prices
from inmo24x7_api.container import get_language_model, get_usage_recorder
from inmo24x7_api.main import app
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker
from test_setup_endpoints import Account

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
import recompute_llm_costs  # noqa: E402

MODEL = "anthropic:claude-test"


def _price(day: date, input_price: str, output_price: str, cached: str | None = None) -> Price:
    return Price(
        MODEL,
        day,
        Decimal(input_price),
        Decimal(output_price),
        Decimal(cached) if cached is not None else None,
    )


class PricedModel(FakeLanguageModel):
    """The fake model's replies with a real model's name and usage."""

    def __init__(self, fail_reply: bool = False) -> None:
        super().__init__()
        self.fail_reply = fail_reply

    @property
    def model_name(self) -> str:
        return MODEL

    def extract(self, request: ExtractionRequest) -> Extraction:
        result = super().extract(request)
        return Extraction(
            values=result.values,
            visitor_name=result.visitor_name,
            contact=result.contact,
            choice_id=result.choice_id,
            wants_human=result.wants_human,
            usage=TokenUsage(1_000, 100, 400, reported=True),
        )

    def compose_reply(self, request: ReplyRequest) -> Reply:
        if self.fail_reply:
            from followup_core.conversation.domain.errors import LlmUnavailableError

            raise LlmUnavailableError("provider down")
        return Reply(super().compose_reply(request).text, TokenUsage(2_000, 300, reported=True))


@pytest.fixture
def owner(client: TestClient, auth) -> Account:
    return Account(client, auth)


@pytest.fixture
def priced(database):
    """The API's recorder with a known price for MODEL."""
    prices = PriceBook([_price(date(2020, 1, 1), "3", "15", "0.3")])
    recorder = SqlAlchemyLlmUsageRecorder(sessionmaker(bind=database), prices)
    app.dependency_overrides[get_usage_recorder] = lambda: recorder
    yield prices


def _rows(db_session) -> list[LlmUsageModel]:
    db_session.expire_all()
    return list(db_session.scalars(select(LlmUsageModel).order_by(LlmUsageModel.created_at)))


# --- prices -----------------------------------------------------------------------------------


def test_cost_counts_cached_input_at_the_cached_price() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=100_000, cached_input_tokens=400_000)
    price = _price(date(2026, 1, 1), "3", "15", "0.3")

    # 600k × 3 + 400k × 0.3 + 100k × 15, per million.
    assert cost_usd(usage, price) == Decimal("1.8") + Decimal("0.12") + Decimal("1.5")
    # Without a cached price, cached input is billed like any input.
    assert cost_usd(usage, _price(date(2026, 1, 1), "3", "15")) == Decimal("4.5")


def test_the_price_in_force_on_the_call_date_applies() -> None:
    prices = PriceBook([_price(date(2026, 11, 1), "3", "15"), _price(date(2026, 12, 1), "2", "10")])
    usage = TokenUsage(1_000_000, 0, reported=True)

    november = price_call(prices, MODEL, usage, datetime(2026, 11, 30, 23, 59, tzinfo=UTC))
    december = price_call(prices, MODEL, usage, datetime(2026, 12, 1, tzinfo=UTC))
    before = price_call(prices, MODEL, usage, datetime(2026, 10, 31, tzinfo=UTC))

    assert (november.cost_usd, november.price_version) == (Decimal(3), "2026-11-01")
    assert (december.cost_usd, december.price_version) == (Decimal(2), "2026-12-01")
    assert (before.cost_usd, before.price_version) == (None, None)
    # Another model has no price; the fake model is free.
    assert price_call(prices, "openai:x", usage, datetime.now(UTC)).cost_usd is None
    assert price_call(prices, "fake", usage, datetime.now(UTC)).cost_usd == Decimal(0)


def test_the_shipped_price_file_loads_and_prices_nothing_yet() -> None:
    prices = parse_prices(PRICES_FILE.read_text(encoding="utf-8"))

    # Empty entries until someone copies the real prices in.
    assert not prices.has_model("anthropic:claude-sonnet-5-5")


def test_the_price_file_is_validated() -> None:
    entry = """
[[price]]
model = "anthropic:claude-test"
effective_from = 2026-11-01
input_per_mtok = "3"
output_per_mtok = "15"
cached_input_per_mtok = ""
source = "https://example.com"
"""
    book = parse_prices(entry)
    assert book.has_model(MODEL)
    price = book.price_for(MODEL, datetime(2026, 11, 2, tzinfo=UTC))
    assert price is not None and price.cached_input_per_mtok is None

    with pytest.raises(PriceFileError, match="two prices"):
        parse_prices(entry + entry)
    with pytest.raises(PriceFileError, match="number"):
        parse_prices(entry.replace('"15"', '"quince"'))
    with pytest.raises(PriceFileError, match="date"):
        parse_prices(entry.replace("2026-11-01", '"noviembre"'))
    with pytest.raises(PriceFileError, match="provider:model"):
        parse_prices(entry.replace(MODEL, "claude"))


# --- recording ---------------------------------------------------------------------------------


def test_each_call_is_a_row_with_its_tokens_and_cost(owner: Account, priced, db_session) -> None:
    app.dependency_overrides[get_language_model] = lambda: PricedModel()

    assert owner.post("/simulator/messages", {"text": "Hola"}).status_code == 200

    rows = _rows(db_session)
    assert [row.operation for row in rows] == ["extract", "compose_reply"]
    extract, reply = rows
    assert (extract.input_tokens, extract.output_tokens, extract.cached_input_tokens) == (
        1_000,
        100,
        400,
    )
    # (600 × 3 + 400 × 0.3 + 100 × 15) / 1M and (2000 × 3 + 300 × 15) / 1M.
    assert extract.cost_usd == Decimal("0.003420")
    assert reply.cost_usd == Decimal("0.010500")
    assert extract.price_version == "2020-01-01"
    assert (extract.provider, extract.model) == ("anthropic", MODEL)
    assert extract.tenant_id == owner.tenant_id
    assert extract.channel == "simulator" and extract.is_test is True
    assert extract.succeeded and extract.usage_reported
    thread_id = db_session.scalar(text("SELECT id FROM conversation_threads"))
    assert extract.thread_id == reply.thread_id == thread_id


def test_usage_is_kept_when_the_turn_rolls_back(owner: Account, priced, db_session) -> None:
    app.dependency_overrides[get_language_model] = lambda: PricedModel(fail_reply=True)

    assert owner.post("/simulator/messages", {"text": "Hola"}).status_code == 503

    # Nothing of the turn was stored, but the provider billed the extraction.
    assert db_session.scalar(text("SELECT count(*) FROM conversation_threads")) == 0
    rows = _rows(db_session)
    assert [(row.operation, row.succeeded) for row in rows] == [
        ("extract", True),
        ("compose_reply", False),
    ]
    assert rows[0].cost_usd == Decimal("0.003420")
    assert (rows[1].input_tokens, rows[1].cost_usd) == (0, Decimal(0))


def test_a_model_without_a_price_stores_no_cost(owner: Account, db_session) -> None:
    # The default test recorder uses the shipped (empty) price file.
    app.dependency_overrides[get_language_model] = lambda: PricedModel()

    assert owner.post("/simulator/messages", {"text": "Hola"}).status_code == 200

    rows = _rows(db_session)
    assert len(rows) == 2
    assert all(row.cost_usd is None and row.price_version is None for row in rows)


def test_providers_without_usage_are_marked(owner: Account, db_session) -> None:
    assert owner.post("/simulator/messages", {"text": "Hola"}).status_code == 200

    rows = _rows(db_session)
    # The fake model reports nothing: zeros, flagged, and free.
    assert {(row.usage_reported, row.input_tokens, row.cost_usd) for row in rows} == {
        (False, 0, Decimal(0))
    }


def test_a_failing_write_never_breaks_the_turn() -> None:
    def broken_sessions():
        raise RuntimeError("database down")

    recorder = SqlAlchemyLlmUsageRecorder(broken_sessions, PriceBook())  # type: ignore[arg-type]
    call = LlmCall(
        tenant_id=uuid4(),
        thread_id=uuid4(),
        channel="whatsapp",
        is_test=False,
        operation=LlmOperation.EXTRACT,
        model=MODEL,
        usage=TokenUsage(),
        latency_ms=10,
        succeeded=True,
        created_at=datetime.now(UTC),
    )

    recorder.record(call)  # does not raise


# --- recompute ---------------------------------------------------------------------------------


def test_recompute_is_a_dry_run_until_apply(owner: Account, database, db_session, capsys) -> None:
    app.dependency_overrides[get_language_model] = lambda: PricedModel()
    assert owner.post("/simulator/messages", {"text": "Hola"}).status_code == 200
    assert all(row.cost_usd is None for row in _rows(db_session))
    sessions = sessionmaker(bind=database)
    prices = PriceBook([_price(date(2020, 1, 1), "3", "15", "0.3")])
    since = datetime.now(UTC).date().isoformat()

    assert recompute_llm_costs.main(["--from", since], sessions, prices) == 0
    assert "2 filas cambiarían" in capsys.readouterr().out
    assert all(row.cost_usd is None for row in _rows(db_session))

    assert recompute_llm_costs.main(["--from", since, "--apply"], sessions, prices) == 0
    output = capsys.readouterr().out
    assert "2 filas actualizadas" in output and "USD 0.0000 → 0.0139" in output
    assert [row.cost_usd for row in _rows(db_session)] == [
        Decimal("0.003420"),
        Decimal("0.010500"),
    ]

    # Nothing left to change.
    assert recompute_llm_costs.main(["--from", since], sessions, prices) == 0
    assert "0 filas cambiarían" in capsys.readouterr().out
