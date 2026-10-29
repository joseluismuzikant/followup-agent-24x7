from uuid import uuid4

import pytest
from followup_core.identity.domain.profile import Profile, Role
from followup_core.tenancy.application.agent_setup import (
    GetAgentSetup,
    ListAgentConfigVersions,
    QuestionDraft,
    SaveAgentSetup,
)
from followup_core.tenancy.domain.agent_config import (
    AgentConfig,
    QualificationQuestion,
    QuestionKind,
    Tone,
)
from followup_core.tenancy.domain.business_settings import TEAM_HOURS_MON_SAT_9_13
from followup_core.tenancy.domain.errors import (
    AgentConfigConflictError,
    InvalidAgentNameError,
    InvalidQuestionsError,
    InvalidTeamHoursError,
    TenantSetupNotFoundError,
)
from tenancy_fakes import (
    InMemoryAgentConfigRepository,
    InMemoryBusinessSettingsRepository,
    InMemoryProfileRepository,
    sample_config,
    sample_defaults,
    sample_draft,
    sample_settings,
)


def _question(key: str = "zone", **kwargs) -> QualificationQuestion:
    values = {"label": "Zona", "kind": QuestionKind.TEXT}
    values.update(kwargs)
    return QualificationQuestion(key, **values)


@pytest.mark.parametrize("name", ["", "   ", "x" * 41])
def test_agent_name_must_have_1_to_40_characters(name: str) -> None:
    with pytest.raises(InvalidAgentNameError):
        sample_config(agent_name=name)


def test_question_rules() -> None:
    with pytest.raises(InvalidQuestionsError):
        _question("Not A Slug")
    with pytest.raises(InvalidQuestionsError):
        _question(label="  ")
    with pytest.raises(InvalidQuestionsError):
        _question(kind=QuestionKind.CHOICE, options=("solo una",))
    with pytest.raises(InvalidQuestionsError):
        sample_config(qualification_questions=(_question("a"), _question("a")))
    with pytest.raises(InvalidQuestionsError):
        sample_config(qualification_questions=tuple(_question(f"q{i}") for i in range(11)))


def test_non_choice_questions_drop_options() -> None:
    assert _question(options=("a", "b")).options == ()


def test_config_round_trips_through_primitives() -> None:
    config = sample_config(tone=Tone.FORMAL)

    assert AgentConfig.from_primitives(config.to_primitives()) == config


def _setup(tenant_id):
    configs = InMemoryAgentConfigRepository()
    settings = InMemoryBusinessSettingsRepository()
    settings.add(sample_settings(tenant_id))
    defaults = sample_defaults()
    return (
        configs,
        settings,
        GetAgentSetup(configs, settings, defaults),
        SaveAgentSetup(configs, settings, defaults),
    )


def test_get_returns_defaults_before_the_first_save() -> None:
    tenant_id = uuid4()
    _, _, get, _ = _setup(tenant_id)

    setup = get.execute(tenant_id)

    assert setup.version == 0
    assert setup.updated_at is None
    assert setup.config == sample_defaults().agent_config


def test_save_creates_versions_only_when_the_config_changes() -> None:
    tenant_id, author = uuid4(), uuid4()
    configs, settings, _, save = _setup(tenant_id)
    current = settings.get(tenant_id)
    assert current is not None
    emails, hours = current.notification_emails, current.team_hours

    first = save.execute(tenant_id, author, sample_draft(), hours, emails)
    same = save.execute(tenant_id, author, sample_draft(), hours, emails)
    changed = save.execute(tenant_id, author, sample_draft(tone=Tone.FORMAL), hours, emails)

    assert (first.version, same.version, changed.version) == (1, 1, 2)
    assert len(configs.versions) == 2
    assert settings.saves == 0


def test_save_updates_hours_and_emails_without_a_new_version() -> None:
    tenant_id = uuid4()
    configs, settings, _, save = _setup(tenant_id)
    save.execute(tenant_id, uuid4(), sample_draft(), TEAM_HOURS_MON_SAT_9_13, ("a@x.com",))

    result = save.execute(
        tenant_id, uuid4(), sample_draft(), TEAM_HOURS_MON_SAT_9_13, ("a@x.com", "b@x.com")
    )

    assert result.version == 1
    assert result.team_hours == TEAM_HOURS_MON_SAT_9_13
    assert result.notification_emails == ("a@x.com", "b@x.com")


def test_save_without_settings_fails() -> None:
    save = SaveAgentSetup(
        InMemoryAgentConfigRepository(), InMemoryBusinessSettingsRepository(), sample_defaults()
    )

    with pytest.raises(TenantSetupNotFoundError):
        save.execute(uuid4(), uuid4(), sample_draft(), (), ("a@x.com",))


def test_invalid_hours_do_not_write_a_version() -> None:
    tenant_id = uuid4()
    configs, _, _, save = _setup(tenant_id)

    with pytest.raises(InvalidTeamHoursError):
        # Overlapping blocks are rejected when the settings are rebuilt.
        from datetime import time

        from followup_core.tenancy.domain.business_settings import ScheduleBlock

        save.execute(
            tenant_id,
            uuid4(),
            sample_draft(),
            (ScheduleBlock(0, time(9), time(13)), ScheduleBlock(0, time(12), time(18))),
            ("a@x.com",),
        )

    assert configs.versions == []


def test_versions_list_is_newest_first_capped_and_has_author_email() -> None:
    tenant_id = uuid4()
    configs, settings, _, save = _setup(tenant_id)
    profiles = InMemoryProfileRepository()
    author = Profile(uuid4(), "Autor@X.com", "Autor", tenant_id, Role.OWNER, False)
    profiles.add(author)
    current = settings.get(tenant_id)
    assert current is not None
    for index in range(25):
        save.execute(
            tenant_id,
            author.id,
            sample_draft(agent_name=f"Agente {index}"),
            current.team_hours,
            current.notification_emails,
        )

    listed = ListAgentConfigVersions(configs, profiles).execute(tenant_id)

    assert len(listed) == 20
    assert listed[0].version == 25
    assert listed[0].author_email == "autor@x.com"


def _new_question(label: str) -> QuestionDraft:
    return QuestionDraft(None, label, QuestionKind.TEXT)


def _keys(setup) -> list[str]:
    return [question.key for question in setup.config.qualification_questions]


def _save(save: SaveAgentSetup, tenant_id, draft):
    return save.execute(tenant_id, uuid4(), draft, (), ("a@x.com",))


def test_new_questions_get_server_assigned_custom_keys() -> None:
    tenant_id = uuid4()
    _, _, _, save = _setup(tenant_id)

    setup = _save(
        save, tenant_id, sample_draft(_new_question("Mascotas"), _new_question("Cochera"))
    )

    assert _keys(setup) == ["operation", "zone", "custom_1", "custom_2"]


def test_deleted_custom_keys_are_never_reused() -> None:
    tenant_id = uuid4()
    _, _, _, save = _setup(tenant_id)
    _save(save, tenant_id, sample_draft(_new_question("Mascotas"), _new_question("Cochera")))
    # Delete custom_2, keep custom_1.
    kept = QuestionDraft("custom_1", "Mascotas", QuestionKind.TEXT)
    _save(save, tenant_id, sample_draft(kept))

    setup = _save(save, tenant_id, sample_draft(kept, _new_question("Balcón")))

    assert _keys(setup) == ["operation", "zone", "custom_1", "custom_3"]


def test_keys_are_counted_per_tenant() -> None:
    tenant_a, tenant_b = uuid4(), uuid4()
    configs, settings, _, save = _setup(tenant_a)
    settings.add(sample_settings(tenant_b))
    _save(save, tenant_a, sample_draft(_new_question("Mascotas"), _new_question("Cochera")))

    setup = _save(save, tenant_b, sample_draft(_new_question("Balcón")))

    assert _keys(setup)[-1] == "custom_1"


@pytest.mark.parametrize("key", ["custom_7", "made_up", "custom_x"])
def test_unknown_keys_are_rejected(key: str) -> None:
    tenant_id = uuid4()
    configs, _, _, save = _setup(tenant_id)

    with pytest.raises(InvalidQuestionsError):
        _save(save, tenant_id, sample_draft(QuestionDraft(key, "Algo", QuestionKind.TEXT)))

    assert configs.versions == []


def test_a_concurrent_save_of_the_same_version_conflicts() -> None:
    tenant_id = uuid4()
    configs, _, _, save = _setup(tenant_id)
    _save(save, tenant_id, sample_draft())
    # Another request read version 1 as latest too, and saved version 2 first.
    stale_latest = configs.latest(tenant_id)
    _save(save, tenant_id, sample_draft(agent_name="Lucía"))
    configs.latest = lambda _tenant_id: stale_latest  # type: ignore[method-assign]

    with pytest.raises(AgentConfigConflictError):
        _save(save, tenant_id, sample_draft(agent_name="Marta"))
