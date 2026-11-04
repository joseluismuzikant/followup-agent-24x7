import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.llm import TokenUsage
from ..domain.usage import LlmCall, PriceBook, price_call
from .models import LlmUsageModel

logger = logging.getLogger("followup.llm_usage")


class SqlAlchemyLlmUsageRecorder:
    """Writes each call in its own short transaction, on sessions that are not the turn's:
    the row survives when the turn rolls back. Any failure is logged and swallowed."""

    def __init__(self, sessions: Callable[[], Session], prices: PriceBook) -> None:
        self._sessions = sessions
        self._prices = prices

    def record(self, call: LlmCall) -> None:
        try:
            priced = price_call(self._prices, call.model, call.usage, call.created_at)
            with self._sessions() as session:
                session.add(
                    LlmUsageModel(
                        id=uuid4(),
                        tenant_id=call.tenant_id,
                        thread_id=call.thread_id,
                        channel=call.channel,
                        is_test=call.is_test,
                        operation=call.operation.value,
                        provider=call.provider,
                        model=call.model,
                        input_tokens=call.usage.input_tokens,
                        output_tokens=call.usage.output_tokens,
                        cached_input_tokens=call.usage.cached_input_tokens,
                        usage_reported=call.usage.reported,
                        latency_ms=call.latency_ms,
                        succeeded=call.succeeded,
                        cost_usd=priced.cost_usd,
                        price_version=priced.price_version,
                        created_at=call.created_at,
                    )
                )
                session.commit()
        except Exception as error:
            logger.warning(
                "llm_usage_write_failed",
                extra={"error": type(error).__name__, "operation": call.operation.value},
            )


@dataclass(frozen=True, slots=True)
class MonthCosts:
    month: str  # YYYY-MM (UTC)
    rows_changed: int
    before_usd: Decimal
    after_usd: Decimal
    # Rows that still have no price after the recompute.
    unpriced: int


def recompute_costs(
    session: Session, prices: PriceBook, since: date, *, apply: bool
) -> list[MonthCosts]:
    """Prices every row from `since` (UTC) again with the current price file. Writes only
    with `apply`; the caller commits."""
    start = datetime.combine(since, time.min, tzinfo=UTC)
    rows = session.scalars(
        select(LlmUsageModel)
        .where(LlmUsageModel.created_at >= start)
        .order_by(LlmUsageModel.created_at)
    ).all()
    months: dict[str, dict[str, Any]] = {}
    for row in rows:
        usage = TokenUsage(
            row.input_tokens, row.output_tokens, row.cached_input_tokens, row.usage_reported
        )
        priced = price_call(prices, row.model, usage, row.created_at)
        month = months.setdefault(
            row.created_at.astimezone(UTC).strftime("%Y-%m"),
            {"changed": 0, "before": Decimal(0), "after": Decimal(0), "unpriced": 0},
        )
        month["before"] += row.cost_usd or 0
        month["after"] += priced.cost_usd or 0
        month["unpriced"] += priced.cost_usd is None
        if (row.cost_usd, row.price_version) != (priced.cost_usd, priced.price_version):
            month["changed"] += 1
            if apply:
                row.cost_usd = priced.cost_usd
                row.price_version = priced.price_version
    return [
        MonthCosts(name, item["changed"], item["before"], item["after"], item["unpriced"])
        for name, item in sorted(months.items())
    ]
