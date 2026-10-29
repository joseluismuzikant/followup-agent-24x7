from collections.abc import Sequence
from datetime import UTC, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.agent_config import AgentConfig
from ..domain.agent_config_repository import AgentConfigVersion
from ..domain.business_settings import BusinessSettings, BusinessType, ScheduleBlock
from ..domain.errors import AgentConfigConflictError
from ..domain.onboarding import Onboarding, OnboardingStep
from .models import AgentConfigVersionModel, BusinessSettingsModel, OnboardingModel


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqlAlchemyOnboardingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tenant_id: UUID) -> Onboarding | None:
        model = self._session.get(OnboardingModel, tenant_id)
        if model is None:
            return None
        return Onboarding(
            tenant_id=model.tenant_id,
            current_step=OnboardingStep(model.current_step),
            completed_steps={
                OnboardingStep(step): _aware(datetime.fromisoformat(completed_at))
                for step, completed_at in model.completed_steps.items()
            },
            finished_at=_aware(model.finished_at) if model.finished_at else None,
        )

    def add(self, onboarding: Onboarding) -> None:
        model = OnboardingModel(tenant_id=onboarding.tenant_id)
        self._apply(model, onboarding)
        self._session.add(model)
        self._session.flush()

    def save(self, onboarding: Onboarding) -> None:
        model = self._session.get(OnboardingModel, onboarding.tenant_id)
        if model is None:
            raise LookupError("Onboarding record does not exist.")
        self._apply(model, onboarding)
        self._session.flush()

    @staticmethod
    def _apply(model: OnboardingModel, onboarding: Onboarding) -> None:
        model.current_step = onboarding.current_step.value
        model.completed_steps = {
            step.value: completed_at.isoformat()
            for step, completed_at in onboarding.completed_steps.items()
        }
        model.finished_at = onboarding.finished_at
        model.updated_at = datetime.now(UTC)


def _time_to_text(value: time) -> str:
    return value.strftime("%H:%M")


class SqlAlchemyBusinessSettingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tenant_id: UUID) -> BusinessSettings | None:
        model = self._session.get(BusinessSettingsModel, tenant_id)
        if model is None:
            return None
        return BusinessSettings(
            tenant_id=model.tenant_id,
            business_type=BusinessType(model.business_type),
            timezone=model.timezone,
            team_hours=tuple(
                ScheduleBlock(
                    weekday=block["weekday"],
                    opens=time.fromisoformat(block["opens"]),
                    closes=time.fromisoformat(block["closes"]),
                )
                for block in model.team_hours
            ),
            notification_emails=tuple(model.notification_emails),
        )

    def add(self, settings: BusinessSettings) -> None:
        model = BusinessSettingsModel(tenant_id=settings.tenant_id)
        self._apply(model, settings)
        self._session.add(model)
        self._session.flush()

    def save(self, settings: BusinessSettings) -> None:
        model = self._session.get(BusinessSettingsModel, settings.tenant_id)
        if model is None:
            raise LookupError("Business settings do not exist.")
        self._apply(model, settings)
        self._session.flush()

    @staticmethod
    def _apply(model: BusinessSettingsModel, settings: BusinessSettings) -> None:
        model.business_type = settings.business_type.value
        model.timezone = settings.timezone
        model.team_hours = [
            {
                "weekday": block.weekday,
                "opens": _time_to_text(block.opens),
                "closes": _time_to_text(block.closes),
            }
            for block in settings.team_hours
        ]
        model.notification_emails = list(settings.notification_emails)
        model.updated_at = datetime.now(UTC)


def _version_to_domain(model: AgentConfigVersionModel) -> AgentConfigVersion:
    return AgentConfigVersion(
        tenant_id=model.tenant_id,
        version=model.version,
        created_at=_aware(model.created_at),
        created_by_profile_id=model.created_by_profile_id,
        config=AgentConfig.from_primitives(model.config),
    )


class SqlAlchemyAgentConfigRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def latest(self, tenant_id: UUID) -> AgentConfigVersion | None:
        versions = self.list_versions(tenant_id, 1)
        return versions[0] if versions else None

    def add_version(self, version: AgentConfigVersion) -> None:
        self._session.add(
            AgentConfigVersionModel(
                id=uuid4(),
                tenant_id=version.tenant_id,
                version=version.version,
                created_at=version.created_at,
                created_by_profile_id=version.created_by_profile_id,
                config=version.config.to_primitives(),
            )
        )
        try:
            self._session.flush()
        except IntegrityError as error:
            # Only the unique (tenant_id, version) constraint can fail here: someone else
            # saved between our read of the latest version and this insert.
            raise AgentConfigConflictError(
                f"Agent config version {version.version} already exists."
            ) from error

    def question_keys(self, tenant_id: UUID) -> set[str]:
        configs = self._session.scalars(
            select(AgentConfigVersionModel.config).where(
                AgentConfigVersionModel.tenant_id == tenant_id
            )
        ).all()
        return {
            question["key"] for config in configs for question in config["qualification_questions"]
        }

    def list_versions(self, tenant_id: UUID, limit: int) -> Sequence[AgentConfigVersion]:
        models = self._session.scalars(
            select(AgentConfigVersionModel)
            .where(AgentConfigVersionModel.tenant_id == tenant_id)
            .order_by(AgentConfigVersionModel.version.desc())
            .limit(limit)
        ).all()
        return [_version_to_domain(model) for model in models]
