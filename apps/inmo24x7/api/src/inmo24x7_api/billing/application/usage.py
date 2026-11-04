from collections.abc import Callable, Iterator
from datetime import datetime
from decimal import Decimal
from functools import reduce
from uuid import UUID

from followup_core.tenancy.domain.errors import TenantNotFoundError

from ..domain.usage import Month, TenantUsage, UsageFigures, UsageReport, sort_by_cost
from ..infrastructure.queries import SqlAlchemyUsageQueries

Clock = Callable[[], datetime]


class GetUsageReport:
    """Consumo: totals and one row per business, the most expensive first."""

    def __init__(self, queries: SqlAlchemyUsageQueries) -> None:
        self._queries = queries

    def execute(self, month: Month) -> UsageReport:
        businesses = sort_by_cost(self._queries.businesses(month))
        totals = reduce(lambda a, b: a + b, (row.figures for row in businesses), UsageFigures())
        return UsageReport(month, totals, businesses)


class GetTenantUsage:
    """One business: its row, the daily cost and conversations, and the splits."""

    def __init__(self, queries: SqlAlchemyUsageQueries) -> None:
        self._queries = queries

    def execute(self, tenant_id: UUID, month: Month) -> TenantUsage:
        rows = self._queries.businesses(month, tenant_id)
        if not rows:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' does not exist.")
        by_operation, by_model = self._queries.splits(tenant_id, month)
        return TenantUsage(
            month=month,
            business=rows[0],
            daily=self._queries.daily(tenant_id, month),
            by_operation=by_operation,
            by_model=by_model,
        )


CSV_HEADER = (
    "Negocio",
    "Plan",
    "Conversaciones",
    "Llamadas al LLM",
    "Tokens de entrada",
    "Tokens de salida",
    "Costo LLM (USD)",
    "Costo por conversación (USD)",
    "Parte del simulador (%)",
    "Plantillas de WhatsApp",
    "Llamadas sin precio",
)


def _number(value: Decimal | float | None, places: int) -> str:
    # Excel in es-AR reads a decimal comma.
    return "" if value is None else f"{value:.{places}f}".replace(".", ",")


def usage_csv(report: UsageReport) -> Iterator[tuple[str, ...]]:
    yield CSV_HEADER
    for row in report.businesses:
        figures = row.figures
        share = figures.test_share
        yield (
            row.name,
            row.plan,
            str(figures.conversations),
            str(figures.llm_calls),
            str(figures.input_tokens),
            str(figures.output_tokens),
            _number(figures.cost_usd, 4),
            _number(figures.cost_per_conversation, 4),
            _number(share * 100 if share is not None else None, 1),
            str(figures.template_messages),
            str(figures.unpriced_calls),
        )
