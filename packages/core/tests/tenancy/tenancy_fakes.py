"""In-memory repositories and builders shared by the tenancy unit tests."""

from datetime import time
from uuid import UUID

from followup_core.identity.domain.profile import Profile
from followup_core.tenancy.application.agent_setup import AgentConfigDraft, QuestionDraft
from followup_core.tenancy.application.defaults import SetupDefaults
from followup_core.tenancy.domain.agent_config import (
    AfterHoursMode,
    AgentConfig,
    QualificationQuestion,
    QuestionKind,
    Tone,
)
from followup_core.tenancy.domain.agent_config_repository import AgentConfigVersion
from followup_core.tenancy.domain.business_settings import (
    DEFAULT_TIMEZONE,
    TEAM_HOURS_WEEKDAYS_9_18,
    BusinessSettings,
    BusinessType,
    ScheduleBlock,
)
from followup_core.tenancy.domain.errors import AgentConfigConflictError
from followup_core.tenancy.domain.onboarding import Onboarding
from followup_core.tenancy.domain.tenant import Tenant


class InMemoryTenantRepository:
    def __init__(self) -> None:
        self.tenants: dict[UUID, Tenant] = {}
        self.slugs: set[str] = set()

    def add(self, tenant: Tenant) -> None:
        self.tenants[tenant.id] = tenant
        self.slugs.add(tenant.slug)

    def save(self, tenant: Tenant) -> None:
        self.tenants[tenant.id] = tenant

    def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        return self.tenants.get(tenant_id)

    def list_page(self, page: int, limit: int) -> list[Tenant]:
        offset = (page - 1) * limit
        return list(self.tenants.values())[offset : offset + limit]

    def count(self) -> int:
        return len(self.tenants)

    def slug_exists(self, slug: str) -> bool:
        return slug in self.slugs


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self.profiles: dict[UUID, Profile] = {}

    def get_by_id(self, user_id: UUID) -> Profile | None:
        return self.profiles.get(user_id)

    def add(self, profile: Profile) -> None:
        self.profiles[profile.id] = profile


class InMemoryOnboardingRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, Onboarding] = {}

    def get(self, tenant_id: UUID) -> Onboarding | None:
        return self.records.get(tenant_id)

    def add(self, onboarding: Onboarding) -> None:
        self.records[onboarding.tenant_id] = onboarding

    def save(self, onboarding: Onboarding) -> None:
        self.records[onboarding.tenant_id] = onboarding


class InMemoryBusinessSettingsRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, BusinessSettings] = {}
        self.saves = 0

    def get(self, tenant_id: UUID) -> BusinessSettings | None:
        return self.records.get(tenant_id)

    def add(self, settings: BusinessSettings) -> None:
        self.records[settings.tenant_id] = settings

    def save(self, settings: BusinessSettings) -> None:
        self.saves += 1
        self.records[settings.tenant_id] = settings


class InMemoryAgentConfigRepository:
    def __init__(self) -> None:
        self.versions: list[AgentConfigVersion] = []

    def latest(self, tenant_id: UUID) -> AgentConfigVersion | None:
        versions = self.list_versions(tenant_id, 1)
        return versions[0] if versions else None

    def get_version(self, tenant_id: UUID, version: int) -> AgentConfigVersion | None:
        for saved in self.versions:
            if (saved.tenant_id, saved.version) == (tenant_id, version):
                return saved
        return None

    def question_keys(self, tenant_id: UUID) -> set[str]:
        return {
            question.key
            for version in self.versions
            if version.tenant_id == tenant_id
            for question in version.config.qualification_questions
        }

    def add_version(self, version: AgentConfigVersion) -> None:
        taken = {(saved.tenant_id, saved.version) for saved in self.versions}
        if (version.tenant_id, version.version) in taken:
            raise AgentConfigConflictError("Version already exists.")
        self.versions.append(version)

    def list_versions(self, tenant_id: UUID, limit: int) -> list[AgentConfigVersion]:
        mine = [version for version in self.versions if version.tenant_id == tenant_id]
        return sorted(mine, key=lambda version: version.version, reverse=True)[:limit]


def sample_config(**overrides) -> AgentConfig:
    values = {
        "agent_name": "Sofía",
        "tone": Tone.WARM,
        "after_hours_mode": AfterHoursMode.KEEP_ANSWERING_AND_PROPOSE_VISIT,
        "qualification_questions": (
            QualificationQuestion(
                "operation", "Comprar o alquilar", QuestionKind.CHOICE, ("compra", "alquiler")
            ),
            QualificationQuestion("zone", "Zona o barrio", QuestionKind.TEXT),
        ),
    }
    values.update(overrides)
    return AgentConfig(**values)


def draft_of(config: AgentConfig) -> AgentConfigDraft:
    return AgentConfigDraft(
        agent_name=config.agent_name,
        tone=config.tone,
        after_hours_mode=config.after_hours_mode,
        qualification_questions=tuple(
            QuestionDraft(
                question.key, question.label, question.kind, question.options, question.enabled
            )
            for question in config.qualification_questions
        ),
    )


def sample_draft(*extra: QuestionDraft, **overrides) -> AgentConfigDraft:
    """The sample config as the panel would send it, plus any extra questions."""
    draft = draft_of(sample_config(**overrides))
    return AgentConfigDraft(
        agent_name=draft.agent_name,
        tone=draft.tone,
        after_hours_mode=draft.after_hours_mode,
        qualification_questions=(*draft.qualification_questions, *extra),
    )


def sample_defaults() -> SetupDefaults:
    return SetupDefaults(
        agent_config=sample_config(),
        team_hours=TEAM_HOURS_WEEKDAYS_9_18,
        timezone=DEFAULT_TIMEZONE,
    )


def sample_settings(tenant_id: UUID, **overrides) -> BusinessSettings:
    values = {
        "tenant_id": tenant_id,
        "business_type": BusinessType.AGENCY,
        "timezone": DEFAULT_TIMEZONE,
        "team_hours": (ScheduleBlock(0, time(9), time(18)),),
        "notification_emails": ("owner@example.com",),
    }
    values.update(overrides)
    return BusinessSettings(**values)
