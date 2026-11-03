"""Day 7 in Tenancy: the audit log keeps personal data out, suspension, plans, and a
business created by an admin that its owner claims at sign-up."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from followup_core.identity.domain.profile import Role
from followup_core.tenancy.application.admin_tenants import (
    CreateBusinessForOwner,
    SetTenantSuspension,
)
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.domain.audit import (
    ActorKind,
    AuditAction,
    AuditEvent,
    hourly_key,
)
from followup_core.tenancy.domain.errors import (
    InvalidAuditDetailsError,
    InvalidSuspensionReasonError,
    OwnerEmailTakenError,
)
from followup_core.tenancy.domain.plans import trial_days_left
from followup_core.tenancy.domain.tenant import Plan, Tenant, TenantStatus
from tenancy_fakes import (
    InMemoryBusinessSettingsRepository,
    InMemoryOnboardingRepository,
    InMemoryOwnerClaims,
    InMemoryProfileRepository,
    InMemoryTenantRepository,
    RecordingAuditLog,
    sample_defaults,
)

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


@pytest.mark.parametrize("key", ["email", "name", "phone", "text", "reason", "token"])
def test_audit_details_never_hold_personal_data(key: str) -> None:
    with pytest.raises(InvalidAuditDetailsError):
        AuditEvent(uuid4(), NOW, ActorKind.USER, AuditAction.SIGN_UP, {key: "x"})


def test_audit_details_are_flat_ids_counts_and_codes() -> None:
    event = AuditEvent(
        uuid4(), NOW, ActorKind.USER, AuditAction.PROPERTIES_IMPORTED, {"created": 3, "code": "x"}
    )
    with pytest.raises(InvalidAuditDetailsError):
        AuditEvent(uuid4(), NOW, ActorKind.USER, AuditAction.SIGN_UP, {"code": {"nested": 1}})
    assert dict(event.details) == {"created": 3, "code": "x"}


def test_system_failures_are_recorded_once_per_hour() -> None:
    tenant = uuid4()
    log = RecordingAuditLog()
    for minutes in (0, 20, 59, 61):
        at = NOW + timedelta(minutes=minutes)
        log.record(
            AuditEvent(
                tenant,
                at,
                ActorKind.SYSTEM,
                AuditAction.SEND_FAILURE,
                {"meta_code": "131026"},
                dedupe_key=hourly_key(AuditAction.SEND_FAILURE, tenant, "131026", at),
            )
        )

    assert len(log.events) == 2


def test_suspend_needs_a_reason_and_keeps_the_first_date() -> None:
    tenant = Tenant.create("Inmobiliaria Sur")

    with pytest.raises(InvalidSuspensionReasonError):
        tenant.suspend("   ", NOW)
    suspended = tenant.suspend("Falta de pago", NOW).suspend("Otra razón", NOW + timedelta(1))
    active = suspended.reactivate()

    assert suspended.is_suspended and suspended.suspended_at == NOW
    assert suspended.suspended_reason == "Otra razón"
    assert (active.status, active.suspended_reason, active.suspended_at) == (
        TenantStatus.ACTIVE,
        None,
        None,
    )


def test_suspension_is_audited_and_reactivating_an_active_tenant_does_nothing() -> None:
    tenants = InMemoryTenantRepository()
    tenant = Tenant.create("Inmobiliaria Sur")
    tenants.add(tenant)
    audit = RecordingAuditLog()
    use_case = SetTenantSuspension(tenants, audit, lambda: NOW)
    admin = uuid4()

    use_case.reactivate(admin, tenant.id)
    use_case.suspend(admin, tenant.id, "Pedido del cliente")
    use_case.reactivate(admin, tenant.id)

    assert audit.actions() == ["tenant_suspended", "tenant_reactivated"]
    assert all(e.actor_kind is ActorKind.ADMIN and e.details == {} for e in audit.events)
    assert tenants.tenants[tenant.id].status is TenantStatus.ACTIVE


def test_trial_days_left_rounds_up_and_pro_has_none() -> None:
    tenant = Tenant.create("Inmobiliaria Sur")
    trial = replace(tenant, trial_ends_at=NOW + timedelta(days=2, hours=1))
    assert trial_days_left(trial, NOW) == 3
    assert trial_days_left(replace(trial, trial_ends_at=NOW - timedelta(1)), NOW) == 0
    assert trial_days_left(replace(trial, plan=Plan.PRO), NOW) is None


def _world():
    tenants = InMemoryTenantRepository()
    profiles = InMemoryProfileRepository()
    onboardings = InMemoryOnboardingRepository()
    settings = InMemoryBusinessSettingsRepository()
    claims = InMemoryOwnerClaims()
    audit = RecordingAuditLog()
    create = CreateBusinessForOwner(
        tenants, profiles, onboardings, settings, claims, sample_defaults(), audit, lambda: NOW
    )
    sign_up = SignUp(tenants, profiles, onboardings, settings, sample_defaults(), claims, audit)
    return tenants, profiles, claims, audit, create, sign_up


def test_the_owner_claims_the_business_an_admin_created() -> None:
    tenants, profiles, claims, audit, create, sign_up = _world()
    tenant = create.execute(uuid4(), "Palermo Propiedades", "inmobiliaria", "Duenia@Palermo.test")

    result = sign_up.execute(uuid4(), "duenia@palermo.test", "Otro nombre", "inmobiliaria")

    assert result.tenant.id == tenant.id and result.tenant.name == "Palermo Propiedades"
    assert result.profile.role is Role.OWNER
    assert len(tenants.tenants) == 1
    assert claims.get_open("duenia@palermo.test") is None
    assert audit.actions() == ["tenant_created_by_admin", "owner_claimed"]


def test_a_second_sign_up_after_the_claim_creates_its_own_business() -> None:
    tenants, _profiles, _claims, _audit, create, sign_up = _world()
    create.execute(uuid4(), "Palermo Propiedades", "inmobiliaria", "duenia@palermo.test")
    sign_up.execute(uuid4(), "duenia@palermo.test", "x", "inmobiliaria")

    other = sign_up.execute(uuid4(), "otra@palermo.test", "Otra", "inmobiliaria")

    assert other.tenant.name == "Otra" and len(tenants.tenants) == 2


def test_an_email_with_an_account_or_a_claim_cannot_get_another_business() -> None:
    _tenants, _profiles, _claims, _audit, create, sign_up = _world()
    sign_up.execute(uuid4(), "ya@tiene.test", "Ya tiene", "inmobiliaria")
    create.execute(uuid4(), "Uno", "inmobiliaria", "pendiente@x.test")

    with pytest.raises(OwnerEmailTakenError):
        create.execute(uuid4(), "Dos", "inmobiliaria", "ya@tiene.test")
    with pytest.raises(OwnerEmailTakenError):
        create.execute(uuid4(), "Tres", "inmobiliaria", "PENDIENTE@x.test")
