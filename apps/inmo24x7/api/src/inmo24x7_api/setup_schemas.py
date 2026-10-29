"""Request/response shapes shared by the agent setup and tenant settings endpoints.

Fields are deliberately loose (plain strings, no length limits): the domain objects
validate them and the routers translate domain errors into stable error codes.
"""

from datetime import time
from typing import Literal

from followup_core.tenancy.application.agent_setup import AgentConfigDraft, QuestionDraft
from followup_core.tenancy.domain.agent_config import (
    AfterHoursMode,
    AgentConfig,
    QuestionKind,
    Tone,
)
from followup_core.tenancy.domain.business_settings import ScheduleBlock
from followup_core.tenancy.domain.errors import InvalidTeamHoursError
from pydantic import BaseModel, Field

ToneName = Literal["warm", "professional", "formal"]
QuestionKindName = Literal["choice", "text", "number", "money", "boolean"]
AfterHoursModeName = Literal["keep_answering_and_propose_visit"]


class QuestionModel(BaseModel):
    key: str
    label: str
    kind: QuestionKindName
    options: list[str] = Field(default_factory=list)
    enabled: bool = True


class AgentConfigModel(BaseModel):
    agent_name: str
    tone: ToneName
    after_hours_mode: AfterHoursModeName
    qualification_questions: list[QuestionModel]


class QuestionInputModel(BaseModel):
    """A question as the panel sends it. New questions have no key: the server assigns one."""

    key: str | None = None
    label: str
    kind: QuestionKindName
    options: list[str] = Field(default_factory=list)
    enabled: bool = True


class AgentConfigInputModel(BaseModel):
    agent_name: str
    tone: ToneName
    after_hours_mode: AfterHoursModeName
    qualification_questions: list[QuestionInputModel]


class ScheduleBlockModel(BaseModel):
    weekday: int
    opens: str
    closes: str


def config_to_model(config: AgentConfig) -> AgentConfigModel:
    return AgentConfigModel(
        agent_name=config.agent_name,
        tone=config.tone.value,  # type: ignore[arg-type]
        after_hours_mode=config.after_hours_mode.value,  # type: ignore[arg-type]
        qualification_questions=[
            QuestionModel(
                key=question.key,
                label=question.label,
                kind=question.kind.value,  # type: ignore[arg-type]
                options=list(question.options),
                enabled=question.enabled,
            )
            for question in config.qualification_questions
        ],
    )


def draft_from_model(model: AgentConfigInputModel) -> AgentConfigDraft:
    return AgentConfigDraft(
        agent_name=model.agent_name,
        tone=Tone(model.tone),
        after_hours_mode=AfterHoursMode(model.after_hours_mode),
        qualification_questions=tuple(
            QuestionDraft(
                key=question.key,
                label=question.label,
                kind=QuestionKind(question.kind),
                options=tuple(question.options),
                enabled=question.enabled,
            )
            for question in model.qualification_questions
        ),
    )


def hours_to_models(blocks: tuple[ScheduleBlock, ...]) -> list[ScheduleBlockModel]:
    return [
        ScheduleBlockModel(
            weekday=block.weekday,
            opens=block.opens.strftime("%H:%M"),
            closes=block.closes.strftime("%H:%M"),
        )
        for block in blocks
    ]


def hours_from_models(models: list[ScheduleBlockModel]) -> tuple[ScheduleBlock, ...]:
    try:
        return tuple(
            ScheduleBlock(
                weekday=model.weekday,
                opens=time.fromisoformat(model.opens),
                closes=time.fromisoformat(model.closes),
            )
            for model in models
        )
    except ValueError as error:
        raise InvalidTeamHoursError("Times must be formatted as HH:MM.") from error
