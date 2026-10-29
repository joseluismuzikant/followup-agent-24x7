from uuid import uuid4

from followup_core.tenancy.application.get_setup_checklist import GetSetupChecklist
from followup_core.tenancy.application.setup_facts import SetupFactProviders
from followup_core.tenancy.application.tenant_settings import UpdateTenantSettings
from followup_core.tenancy.domain.agent_config_repository import AgentConfigVersion
from followup_core.tenancy.domain.business_settings import BusinessType
from followup_core.tenancy.domain.setup_checklist import ChecklistItemKey
from followup_core.tenancy.domain.tenant import Tenant
from tenancy_fakes import (
    InMemoryAgentConfigRepository,
    InMemoryBusinessSettingsRepository,
    InMemoryTenantRepository,
    sample_config,
    sample_settings,
)


def test_renaming_keeps_the_slug() -> None:
    tenants = InMemoryTenantRepository()
    settings = InMemoryBusinessSettingsRepository()
    tenant = Tenant.create("Inmobiliaria Sur")
    tenants.add(tenant)
    settings.add(sample_settings(tenant.id))

    view = UpdateTenantSettings(tenants, settings).execute(
        tenant.id,
        "Sur Propiedades",
        BusinessType.NETWORK,
        (),
        ("nuevo@example.com",),
    )

    assert view.tenant.name == "Sur Propiedades"
    assert view.tenant.slug == "inmobiliaria-sur"
    stored_tenant, stored_settings = tenants.get_by_id(tenant.id), settings.get(tenant.id)
    assert stored_tenant is not None and stored_settings is not None
    assert stored_tenant.name == "Sur Propiedades"
    assert stored_settings.business_type is BusinessType.NETWORK
    assert stored_settings.team_hours == ()


def test_checklist_counts_only_known_facts() -> None:
    tenant_id = uuid4()
    configs = InMemoryAgentConfigRepository()
    use_case = GetSetupChecklist(configs, SetupFactProviders())

    before = use_case.execute(tenant_id)
    assert before.ready_count == 1 and before.total == 5

    configs.add_version(AgentConfigVersion(tenant_id, 1, _now(), uuid4(), sample_config()))
    after = use_case.execute(tenant_id)
    assert after.ready_count == 2
    assert {item.key for item in after.items if item.done} == {
        ChecklistItemKey.ACCOUNT,
        ChecklistItemKey.AGENT,
    }


def test_a_provider_plugs_in_a_later_fact() -> None:
    providers = SetupFactProviders(whatsapp_connected=lambda _tenant_id: True)

    checklist = GetSetupChecklist(InMemoryAgentConfigRepository(), providers).execute(uuid4())

    assert checklist.facts.whatsapp_connected is True
    assert checklist.facts.agent_tested is False
    assert checklist.ready_count == 2


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)
