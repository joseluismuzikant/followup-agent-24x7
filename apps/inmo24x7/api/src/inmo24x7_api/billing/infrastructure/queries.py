"""Consumo in SQL across contexts (llm_usage, conversations, WhatsApp sends), per UTC month.
Platform admins' own tenants are left out, like on S8."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..domain.usage import BusinessUsage, DailyUsage, Month, UsageFigures, UsageSplit

_BUSINESSES = text(
    """
    WITH usage AS (
      SELECT tenant_id, count(*) AS calls, sum(input_tokens) AS input_tokens,
             sum(output_tokens) AS output_tokens, sum(cost_usd) AS cost,
             sum(cost_usd) FILTER (WHERE is_test) AS test_cost,
             count(*) FILTER (WHERE cost_usd IS NULL) AS unpriced,
             count(*) FILTER (WHERE NOT usage_reported) AS unreported
      FROM llm_usage
      WHERE created_at >= :start AND created_at < :end
      GROUP BY tenant_id
    ),
    conversations AS (
      SELECT th.tenant_id, count(DISTINCT th.id) AS conversations
      FROM conversation_messages m
      JOIN conversation_threads th ON th.id = m.thread_id
      WHERE m.direction = 'inbound' AND m.created_at >= :start AND m.created_at < :end
      GROUP BY th.tenant_id
    ),
    templates AS (
      SELECT th.tenant_id, count(*) AS templates
      FROM whatsapp_outbound o
      JOIN conversation_messages m ON m.id = o.message_id
      JOIN conversation_threads th ON th.id = m.thread_id
      WHERE o.body ->> 'type' = 'template' AND o.sent_at >= :start AND o.sent_at < :end
      GROUP BY th.tenant_id
    )
    SELECT t.id, t.name, t.plan,
           coalesce(u.calls, 0) AS calls, coalesce(u.input_tokens, 0) AS input_tokens,
           coalesce(u.output_tokens, 0) AS output_tokens, coalesce(u.cost, 0) AS cost,
           coalesce(u.test_cost, 0) AS test_cost, coalesce(u.unpriced, 0) AS unpriced,
           coalesce(u.unreported, 0) AS unreported,
           coalesce(c.conversations, 0) AS conversations,
           coalesce(tp.templates, 0) AS templates
    FROM tenants t
    LEFT JOIN usage u ON u.tenant_id = t.id
    LEFT JOIN conversations c ON c.tenant_id = t.id
    LEFT JOIN templates tp ON tp.tenant_id = t.id
    WHERE NOT EXISTS (
      SELECT 1 FROM profiles a WHERE a.tenant_id = t.id AND a.is_platform_admin
    )
      AND (CAST(:tenant_id AS uuid) IS NULL OR t.id = CAST(:tenant_id AS uuid))
    """
)

_DAILY = text(
    """
    WITH days AS (
      -- UTC days as plain timestamps, whatever the session's time zone.
      SELECT generate_series(CAST(:start AS timestamptz) AT TIME ZONE 'UTC',
                             CAST(:end AS timestamptz) AT TIME ZONE 'UTC' - interval '1 day',
                             interval '1 day') AS day
    ),
    cost AS (
      SELECT date_trunc('day', created_at AT TIME ZONE 'UTC') AS day, sum(cost_usd) AS cost
      FROM llm_usage
      WHERE tenant_id = :tenant_id AND created_at >= :start AND created_at < :end
      GROUP BY 1
    ),
    conversations AS (
      SELECT date_trunc('day', m.created_at AT TIME ZONE 'UTC') AS day,
             count(DISTINCT th.id) AS conversations
      FROM conversation_messages m
      JOIN conversation_threads th ON th.id = m.thread_id
      WHERE th.tenant_id = :tenant_id AND m.direction = 'inbound'
        AND m.created_at >= :start AND m.created_at < :end
      GROUP BY 1
    )
    SELECT CAST(d.day AS date) AS day, coalesce(c.cost, 0) AS cost,
           coalesce(v.conversations, 0) AS conversations
    FROM days d
    LEFT JOIN cost c ON c.day = d.day
    LEFT JOIN conversations v ON v.day = d.day
    ORDER BY d.day
    """
)

_SPLIT = """
    SELECT {column} AS key, count(*) AS calls, sum(input_tokens) AS input_tokens,
           sum(output_tokens) AS output_tokens, coalesce(sum(cost_usd), 0) AS cost,
           count(*) FILTER (WHERE cost_usd IS NULL) AS unpriced
    FROM llm_usage
    WHERE tenant_id = :tenant_id AND created_at >= :start AND created_at < :end
    GROUP BY {column}
    ORDER BY cost DESC, key
"""
_BY_OPERATION = text(_SPLIT.format(column="operation"))
_BY_MODEL = text(_SPLIT.format(column="model"))

_OVER_LIMIT = text(
    """
    SELECT u.tenant_id, t.name, sum(u.cost_usd) AS cost
    FROM llm_usage u
    JOIN tenants t ON t.id = u.tenant_id
    WHERE u.created_at >= :start AND u.created_at < :end
    GROUP BY u.tenant_id, t.name
    HAVING sum(u.cost_usd) >= :limit
       AND NOT EXISTS (
         SELECT 1 FROM audit_events e
         WHERE e.dedupe_key = 'llm_cost_alert:' || u.tenant_id || ':' || :month
       )
    ORDER BY u.tenant_id
    """
)


def _figures(row: Any) -> UsageFigures:
    return UsageFigures(
        llm_calls=row.calls,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cost_usd=Decimal(row.cost),
        test_cost_usd=Decimal(row.test_cost),
        unpriced_calls=row.unpriced,
        unreported_calls=row.unreported,
        conversations=row.conversations,
        template_messages=row.templates,
    )


def _split(row: Any) -> UsageSplit:
    return UsageSplit(
        key=row.key,
        llm_calls=row.calls,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cost_usd=Decimal(row.cost),
        unpriced_calls=row.unpriced,
    )


class SqlAlchemyUsageQueries:
    def __init__(self, session: Session) -> None:
        self._session = session

    def businesses(self, month: Month, tenant_id: UUID | None = None) -> list[BusinessUsage]:
        rows = self._session.execute(
            _BUSINESSES,
            {"start": month.start, "end": month.end, "tenant_id": tenant_id},
        )
        return [BusinessUsage(row.id, row.name, row.plan, _figures(row)) for row in rows]

    def daily(self, tenant_id: UUID, month: Month) -> list[DailyUsage]:
        rows = self._session.execute(
            _DAILY, {"start": month.start, "end": month.end, "tenant_id": tenant_id}
        )
        return [DailyUsage(row.day, Decimal(row.cost), row.conversations) for row in rows]

    def splits(
        self, tenant_id: UUID, month: Month
    ) -> tuple[Sequence[UsageSplit], Sequence[UsageSplit]]:
        """By operation and by model."""
        params = {"start": month.start, "end": month.end, "tenant_id": tenant_id}
        return (
            [_split(row) for row in self._session.execute(_BY_OPERATION, params)],
            [_split(row) for row in self._session.execute(_BY_MODEL, params)],
        )

    def over_limit(self, month: Month, limit: Decimal) -> list[tuple[UUID, str, Decimal]]:
        """Businesses at or over `limit` this month that were not alerted yet."""
        rows = self._session.execute(
            _OVER_LIMIT,
            {"start": month.start, "end": month.end, "limit": limit, "month": str(month)},
        )
        return [(row.tenant_id, row.name, Decimal(row.cost)) for row in rows]
