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
    # A voice note to text (TRANSCRIBE_MODEL): billed by `audio_seconds`, no tokens.
    TRANSCRIBE = "transcribe"


SECONDS_PER_HOUR = Decimal(3600)


@dataclass(frozen=True, slots=True)
class LlmCall:
    tenant_id: UUID
    # None for a transcription (it runs before the turn creates the thread).
    thread_id: UUID | None
    channel: str
    is_test: bool
    operation: LlmOperation
    # LLM_MODEL as configured ("anthropic:claude-sonnet-5-5"), or the fake model's name.
    model: str
    usage: TokenUsage
    latency_ms: int
    succeeded: bool
    created_at: datetime
    audio_seconds: float | None = None

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


@dataclass(frozen=True, slots=True)
class AudioPrice:
    """USD per hour of audio (transcription), billed by the second, from `effective_from`."""

    model: str
    effective_from: date
    usd_per_hour: Decimal
    source: str = ""

    @property
    def version(self) -> str:
        return self.effective_from.isoformat()


def _newest_first[T: (Price, AudioPrice)](items: Iterable[T]) -> Mapping[str, Sequence[T]]:
    by_model: dict[str, list[T]] = {}
    for item in items:
        by_model.setdefault(item.model, []).append(item)
    return {
        model: sorted(group, key=lambda item: item.effective_from, reverse=True)
        for model, group in by_model.items()
    }


class PriceBook:
    """Prices by model; the newest one whose date has started applies. Token prices and
    audio (per-minute) prices are kept apart."""

    def __init__(
        self, prices: Iterable[Price] = (), audio_prices: Iterable[AudioPrice] = ()
    ) -> None:
        self._prices = _newest_first(prices)
        self._audio = _newest_first(audio_prices)

    def price_for(self, model: str, at: datetime) -> Price | None:
        day = at.date()
        return next(
            (price for price in self._prices.get(model, ()) if price.effective_from <= day),
            None,
        )

    def audio_price_for(self, model: str, at: datetime) -> AudioPrice | None:
        day = at.date()
        return next(
            (price for price in self._audio.get(model, ()) if price.effective_from <= day),
            None,
        )

    def has_model(self, model: str) -> bool:
        return model in self._prices

    def has_audio_model(self, model: str) -> bool:
        return model in self._audio


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


def audio_cost_usd(seconds: float, price: AudioPrice) -> Decimal:
    """Billed by the second, a started second counting whole (DeepSeek's rule; OpenAI's
    per-minute estimate is spread the same way)."""
    whole = Decimal(int(-(-seconds // 1)))
    return (whole * price.usd_per_hour / SECONDS_PER_HOUR).quantize(Decimal("0.000001"))


def price_call(
    prices: PriceBook,
    model: str,
    usage: TokenUsage,
    at: datetime,
    audio_seconds: float | None = None,
    operation: str | None = None,
) -> PricedCost:
    provider, _, _ = model.partition(":")
    if provider in FREE_PROVIDERS:
        return PricedCost(Decimal(0), None)
    if operation == LlmOperation.TRANSCRIBE.value:
        audio = prices.audio_price_for(model, at)
        if audio is None or audio_seconds is None:
            return PricedCost(None, None)
        return PricedCost(audio_cost_usd(audio_seconds, audio), audio.version)
    price = prices.price_for(model, at)
    if price is None:
        return PricedCost(None, None)
    return PricedCost(cost_usd(usage, price), price.version)


class LlmUsageRecorder(Protocol):
    def record(self, call: LlmCall) -> None:
        """Stores the call. Never raises: a failure to record must not break a turn."""
        ...
