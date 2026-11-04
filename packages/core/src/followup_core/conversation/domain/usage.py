"""What each language model call used and cost.

Every call is recorded (successful or not, simulator or real lead), outside the turn's
transaction: the provider charges for the tokens even when the turn later rolls back.
Prices are versioned by the date they take effect; a call is priced with the price in force
when it was made, and a model without a price has no cost (never a guessed one).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from .llm import TokenUsage

TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)
# The template-based fake model of development and the rehearsal: free, not a price.
FREE_PROVIDERS = frozenset({"fake"})


class LlmOperation(StrEnum):
    EXTRACT = "extract"
    COMPOSE_REPLY = "compose_reply"


@dataclass(frozen=True, slots=True)
class LlmCall:
    tenant_id: UUID
    thread_id: UUID
    channel: str
    is_test: bool
    operation: LlmOperation
    # LLM_MODEL as configured ("anthropic:claude-sonnet-5-5"), or the fake model's name.
    model: str
    usage: TokenUsage
    latency_ms: int
    succeeded: bool
    created_at: datetime

    @property
    def provider(self) -> str:
        provider, _, _ = self.model.partition(":")
        return provider


@dataclass(frozen=True, slots=True)
class Price:
    """USD per million tokens, in force from `effective_from` (UTC)."""

    model: str
    effective_from: date
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    # None: cached input is billed like any input.
    cached_input_per_mtok: Decimal | None = None
    source: str = ""

    @property
    def version(self) -> str:
        return self.effective_from.isoformat()


class PriceBook:
    """Prices by model; the newest one whose date has started applies."""

    def __init__(self, prices: Iterable[Price] = ()) -> None:
        by_model: dict[str, list[Price]] = {}
        for price in prices:
            by_model.setdefault(price.model, []).append(price)
        self._prices: Mapping[str, Sequence[Price]] = {
            model: sorted(items, key=lambda item: item.effective_from, reverse=True)
            for model, items in by_model.items()
        }

    def price_for(self, model: str, at: datetime) -> Price | None:
        day = at.date()
        return next(
            (price for price in self._prices.get(model, ()) if price.effective_from <= day),
            None,
        )

    def has_model(self, model: str) -> bool:
        return model in self._prices


def cost_usd(usage: TokenUsage, price: Price) -> Decimal:
    cached = min(usage.cached_input_tokens, usage.input_tokens)
    cached_rate = (
        price.cached_input_per_mtok
        if price.cached_input_per_mtok is not None
        else price.input_per_mtok
    )
    total = (
        (usage.input_tokens - cached) * price.input_per_mtok
        + cached * cached_rate
        + usage.output_tokens * price.output_per_mtok
    )
    return (total / TOKENS_PER_PRICE_UNIT).quantize(Decimal("0.000001"))


@dataclass(frozen=True, slots=True)
class PricedCost:
    cost_usd: Decimal | None
    price_version: str | None


def price_call(prices: PriceBook, model: str, usage: TokenUsage, at: datetime) -> PricedCost:
    provider, _, _ = model.partition(":")
    if provider in FREE_PROVIDERS:
        return PricedCost(Decimal(0), None)
    price = prices.price_for(model, at)
    if price is None:
        return PricedCost(None, None)
    return PricedCost(cost_usd(usage, price), price.version)


class LlmUsageRecorder(Protocol):
    def record(self, call: LlmCall) -> None:
        """Stores the call. Never raises: a failure to record must not break a turn."""
        ...
