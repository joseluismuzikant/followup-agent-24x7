"""Plans, read-only for the MVP: what each one allows and how the backoffice labels it. No
enforcement and no billing yet."""

from dataclasses import dataclass
from datetime import datetime
from math import ceil

from .tenant import Plan, Tenant

MONTHLY_CONVERSATIONS = 1_000


@dataclass(frozen=True, slots=True)
class PlanInfo:
    plan: Plan
    name: str
    monthly_conversations: int


PLANS: tuple[PlanInfo, ...] = (
    PlanInfo(Plan.TRIAL, "Prueba", MONTHLY_CONVERSATIONS),
    PlanInfo(Plan.PRO, "Pro", MONTHLY_CONVERSATIONS),
)


def plan_info(plan: Plan) -> PlanInfo:
    return next(item for item in PLANS if item.plan is plan)


def trial_days_left(tenant: Tenant, now: datetime) -> int | None:
    """Whole days left in the trial, rounded up (0 once it ended); None on a paid plan."""
    if tenant.plan is not Plan.TRIAL:
        return None
    seconds = (tenant.trial_ends_at - now).total_seconds()
    return max(0, ceil(seconds / 86_400))
