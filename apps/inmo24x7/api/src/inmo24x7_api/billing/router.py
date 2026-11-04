"""Backoffice Consumo (platform admins only): LLM cost, conversations and WhatsApp templates
per business and UTC month, one business's daily detail, and the table as CSV."""

import csv
import io
import logging
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from followup_core.identity.domain.profile import Profile
from followup_core.tenancy.domain.errors import TenantNotFoundError
from pydantic import BaseModel

from ..auth import require_platform_admin
from ..http_errors import ApiError
from .application.usage import GetTenantUsage, GetUsageReport, usage_csv
from .domain.usage import BusinessUsage, InvalidMonthError, Month, UsageFigures, UsageSplit

AdminDep = Annotated[Profile, Depends(require_platform_admin)]
Clock = Callable[[], datetime]
MonthQuery = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM (UTC)")]

logger = logging.getLogger("inmo24x7.billing")


class UsageFiguresRead(BaseModel):
    llm_calls: int
    input_tokens: int
    output_tokens: int
    # Decimal amounts as strings ("0.012345"), so nothing is rounded on the way.
    cost_usd: str
    cost_per_conversation_usd: str | None
    # The simulator's share of the cost, 0..1; null without cost.
    test_share: float | None
    conversations: int
    template_messages: int
    # Calls of a model without a price: the cost is incomplete.
    unpriced_calls: int
    # Calls whose provider reported no usage ("sin datos").
    unreported_calls: int


class BusinessUsageRead(BaseModel):
    tenant_id: UUID
    name: str
    plan: str
    figures: UsageFiguresRead


class UsageReportRead(BaseModel):
    month: str
    totals: UsageFiguresRead
    businesses: list[BusinessUsageRead]


class DailyUsageRead(BaseModel):
    day: date
    cost_usd: str
    conversations: int


class UsageSplitRead(BaseModel):
    key: str
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: str
    unpriced_calls: int


class TenantUsageRead(BaseModel):
    month: str
    business: BusinessUsageRead
    daily: list[DailyUsageRead]
    by_operation: list[UsageSplitRead]
    by_model: list[UsageSplitRead]


def _figures(figures: UsageFigures) -> UsageFiguresRead:
    per_conversation = figures.cost_per_conversation
    return UsageFiguresRead(
        llm_calls=figures.llm_calls,
        input_tokens=figures.input_tokens,
        output_tokens=figures.output_tokens,
        cost_usd=f"{figures.cost_usd:.6f}",
        cost_per_conversation_usd=f"{per_conversation:.6f}"
        if per_conversation is not None
        else None,
        test_share=figures.test_share,
        conversations=figures.conversations,
        template_messages=figures.template_messages,
        unpriced_calls=figures.unpriced_calls,
        unreported_calls=figures.unreported_calls,
    )


def _business(row: BusinessUsage) -> BusinessUsageRead:
    return BusinessUsageRead(
        tenant_id=row.tenant_id, name=row.name, plan=row.plan, figures=_figures(row.figures)
    )


def _split(split: UsageSplit) -> UsageSplitRead:
    return UsageSplitRead(
        key=split.key,
        llm_calls=split.llm_calls,
        input_tokens=split.input_tokens,
        output_tokens=split.output_tokens,
        cost_usd=f"{split.cost_usd:.6f}",
        unpriced_calls=split.unpriced_calls,
    )


def build_usage_router(
    report_factory: Callable[..., GetUsageReport],
    tenant_factory: Callable[..., GetTenantUsage],
    clock: Clock,
) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["backoffice"])

    def month_of(value: str | None) -> Month:
        if not value:
            return Month.of(clock())
        try:
            return Month.parse(value)
        except InvalidMonthError as error:
            raise ApiError(422, "validation_error") from error

    @router.get("/usage", response_model=UsageReportRead)
    def usage(
        _admin: AdminDep,
        use_case: Annotated[GetUsageReport, Depends(report_factory)],
        month: MonthQuery = None,
    ) -> UsageReportRead:
        report = use_case.execute(month_of(month))
        return UsageReportRead(
            month=str(report.month),
            totals=_figures(report.totals),
            businesses=[_business(row) for row in report.businesses],
        )

    # Declared before /usage/{tenant_id}, which would otherwise take "export.csv" as an id.
    @router.get(
        "/usage/export.csv",
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}}},
    )
    def usage_export(
        _admin: AdminDep,
        use_case: Annotated[GetUsageReport, Depends(report_factory)],
        month: MonthQuery = None,
    ) -> Response:
        report = use_case.execute(month_of(month))
        buffer = io.StringIO()
        # Excel in es-AR expects ";" and needs the BOM to read UTF-8.
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        for row in usage_csv(report):
            writer.writerow(row)
        logger.info("usage_exported", extra={"rows": len(report.businesses)})
        return Response(
            content="﻿" + buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="consumo-{report.month}.csv"'},
        )

    @router.get("/usage/{tenant_id}", response_model=TenantUsageRead)
    def tenant_usage(
        tenant_id: UUID,
        _admin: AdminDep,
        use_case: Annotated[GetTenantUsage, Depends(tenant_factory)],
        month: MonthQuery = None,
    ) -> TenantUsageRead:
        try:
            detail = use_case.execute(tenant_id, month_of(month))
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error
        return TenantUsageRead(
            month=str(detail.month),
            business=_business(detail.business),
            daily=[
                DailyUsageRead(
                    day=d.day, cost_usd=f"{d.cost_usd:.6f}", conversations=d.conversations
                )
                for d in detail.daily
            ],
            by_operation=[_split(item) for item in detail.by_operation],
            by_model=[_split(item) for item in detail.by_model],
        )

    return router
