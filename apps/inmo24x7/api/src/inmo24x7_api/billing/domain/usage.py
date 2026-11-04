"""The Consumo read model: what each business used and cost in a UTC month.

Costs are the sum of priced calls only; calls of a model without a price are counted apart
(`unpriced_calls`) so the screen can say the total is incomplete instead of guessing.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class InvalidMonthError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Month:
    year: int
    month: int

    @classmethod
    def parse(cls, value: str) -> "Month":
        match = _MONTH.fullmatch(value.strip())
        if not match:
            raise InvalidMonthError(value)
        return cls(int(match.group(1)), int(match.group(2)))

    @classmethod
    def of(cls, at: datetime) -> "Month":
        at = at.astimezone(UTC)
        return cls(at.year, at.month)

    @property
    def start(self) -> datetime:
        return datetime(self.year, self.month, 1, tzinfo=UTC)

    @property
    def end(self) -> datetime:
        """The first instant of the next month (ranges are half-open)."""
        if self.month == 12:
            return datetime(self.year + 1, 1, 1, tzinfo=UTC)
        return datetime(self.year, self.month + 1, 1, tzinfo=UTC)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True, slots=True)
class UsageFigures:
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    # Of cost_usd, what simulator tests used.
    test_cost_usd: Decimal = Decimal(0)
    unpriced_calls: int = 0
    unreported_calls: int = 0
    # Threads with an inbound message in the month (simulator ones included).
    conversations: int = 0
    # Template messages Meta accepted in the month (Meta bills them; no price here).
    template_messages: int = 0

    @property
    def cost_per_conversation(self) -> Decimal | None:
        if not self.conversations:
            return None
        return (self.cost_usd / self.conversations).quantize(Decimal("0.000001"))

    @property
    def test_share(self) -> float | None:
        """The simulator's share of the cost, 0..1."""
        if not self.cost_usd:
            return None
        return float(self.test_cost_usd / self.cost_usd)

    def __add__(self, other: "UsageFigures") -> "UsageFigures":
        return UsageFigures(
            self.llm_calls + other.llm_calls,
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cost_usd + other.cost_usd,
            self.test_cost_usd + other.test_cost_usd,
            self.unpriced_calls + other.unpriced_calls,
            self.unreported_calls + other.unreported_calls,
            self.conversations + other.conversations,
            self.template_messages + other.template_messages,
        )


@dataclass(frozen=True, slots=True)
class BusinessUsage:
    tenant_id: UUID
    name: str
    plan: str
    figures: UsageFigures


@dataclass(frozen=True, slots=True)
class UsageReport:
    month: Month
    totals: UsageFigures
    businesses: Sequence[BusinessUsage]


@dataclass(frozen=True, slots=True)
class DailyUsage:
    day: date
    cost_usd: Decimal
    conversations: int


@dataclass(frozen=True, slots=True)
class UsageSplit:
    key: str  # an operation or a model
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    unpriced_calls: int


@dataclass(frozen=True, slots=True)
class TenantUsage:
    month: Month
    business: BusinessUsage
    daily: Sequence[DailyUsage]
    by_operation: Sequence[UsageSplit]
    by_model: Sequence[UsageSplit]


def sort_by_cost(rows: Sequence[BusinessUsage]) -> list[BusinessUsage]:
    return sorted(rows, key=lambda row: (-row.figures.cost_usd, row.name.lower()))
