"""Backoffice parity (S8, S9), suspension and system health against the test database."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from inmo24x7_api.backoffice.domain.rules import (
    Onboarding,
    TenantRow,
    WhatsAppBadge,
    needs_help,
    whatsapp_badge,
)
from inmo24x7_api.container import get_messaging_services
from inmo24x7_api.main import app
from test_setup_endpoints import Account, _body
from whatsapp_fakes import (
    FakeGraph,
    WhatsAppWorld,
    build_services,
    connect,
    make_sessions,
)

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


class World(WhatsAppWorld):
    owner: Account
    admin: Account

    def admin_get(self, path: str):
        return self.client.get(path, headers=self.admin.headers)

    def admin_post(self, path: str, body: dict | None = None):
        return self.client.post(path, json=body or {}, headers=self.admin.headers)


@pytest.fixture
def world(client: TestClient, auth, database):
    graph = FakeGraph()
    services = build_services(graph)
    app.dependency_overrides[get_messaging_services] = lambda: services
    world = World(client, make_sessions(database), services, graph)
    world.owner = Account(client, auth)
    setup = world.owner.get("/agent-setup").json()
    always = [{"weekday": day, "opens": "00:00", "closes": "23:30"} for day in range(7)]
    world.owner.put("/agent-setup", _body(setup, business_hours=always))
    world.admin = Account(client, auth, "Plataforma")
    auth.make_admin(world.admin.user_id)
    yield world
    app.dependency_overrides.pop(get_messaging_services, None)


def _row(**changes) -> TenantRow:
    base = {
        "id": uuid4(),
        "name": "Inmo",
        "suspended": False,
        "plan": "trial",
        "trial_ends_at": NOW + timedelta(days=10),
        "created_at": NOW - timedelta(hours=1),
        "owner_email": "a@b.test",
        "owner_pending": False,
        "onboarding": Onboarding(True, True, True, True, finished=True),
        "whatsapp_status": "connected",
        "business_verification": "verified",
        "leads_last_7_days": 0,
    }
    return TenantRow(**{**base, **changes})


# --- Rules ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, False),
        ({"whatsapp_status": "error"}, True),
        ({"onboarding": Onboarding(True, False, False, False, finished=False)}, False),
        (
            {
                "onboarding": Onboarding(True, False, False, False, finished=False),
                "created_at": NOW - timedelta(hours=49),
            },
            True,
        ),
        ({"trial_ends_at": NOW + timedelta(days=2), "whatsapp_status": None}, True),
        ({"trial_ends_at": NOW + timedelta(days=2)}, False),  # it has WhatsApp
        ({"trial_ends_at": NOW + timedelta(days=2), "plan": "pro", "whatsapp_status": None}, False),
    ],
)
def test_needs_help(changes: dict, expected: bool) -> None:
    assert needs_help(_row(**changes), NOW) is expected


@pytest.mark.parametrize(
    ("status", "verification", "badge"),
    [
        (None, None, WhatsAppBadge.NOT_CONNECTED),
        ("disconnected", "verified", WhatsAppBadge.NOT_CONNECTED),
        ("error", "verified", WhatsAppBadge.ACTION_REQUIRED),
        ("connected", "failed", WhatsAppBadge.ACTION_REQUIRED),
        ("connected", "pending", WhatsAppBadge.VERIFICATION_PENDING),
        ("connected", "unknown", WhatsAppBadge.CONNECTED),
        ("connected", "verified", WhatsAppBadge.CONNECTED),
    ],
)
def test_whatsapp_badge(status, verification, badge) -> None:
    assert whatsapp_badge(status, verification) is badge


# --- S8 / S9 ---------------------------------------------------------------------------------


def test_the_backoffice_is_admin_only(world: World) -> None:
    for path in ("/admin/tenants", f"/admin/tenants/{world.owner.tenant_id}", "/admin/system"):
        assert world.owner.get(path).status_code == 403
    assert world.owner.post(f"/admin/tenants/{world.owner.tenant_id}/suspend", {}).status_code in (
        403,
        422,
    )


def test_the_list_has_kpis_filters_search_and_badges(world: World, client, auth) -> None:
    stuck = Account(client, auth, "Belgrano Hogar")
    world.execute(
        "UPDATE tenants SET created_at = now() - interval '3 days' WHERE id = :t", t=stuck.tenant_id
    )
    assert connect(client, world.admin.headers, world.owner.tenant_id).status_code == 200

    everything = world.admin_get("/admin/tenants").json()
    names = [item["name"] for item in everything["items"]]
    assert names == ["Inmobiliaria Sur", "Belgrano Hogar"]  # newest first; no Plataforma
    assert everything["kpis"] == {
        "active": 2,
        "trial": 2,
        "onboarding_unfinished": 2,
        "whatsapp_problems": 0,
    }
    sur = everything["items"][0]
    assert sur["whatsapp"] == "connected" and sur["owner_email"] == world.owner.email
    assert (sur["onboarding_done"], sur["onboarding_total"]) == (3, 5)
    assert sur["plan"] == {"plan": "trial", "name": "Prueba", "trial_days_left": 14}

    help_ = world.admin_get("/admin/tenants?filter=needs_help").json()
    assert [item["name"] for item in help_["items"]] == ["Belgrano Hogar"]
    by_email = world.admin_get(f"/admin/tenants?q={world.owner.email[:8]}").json()
    assert [item["name"] for item in by_email["items"]] == ["Inmobiliaria Sur"]
    assert world.admin_get("/admin/tenants?q=belgrano").json()["total"] == 1

    world.execute("UPDATE whatsapp_connections SET status = 'error', last_error_code = '190'")
    problems = world.admin_get("/admin/tenants").json()
    assert problems["kpis"]["whatsapp_problems"] == 1
    assert problems["items"][0]["whatsapp"] == "action_required"


def test_the_detail_masks_the_waba_and_shows_activity_usage_and_users(world: World) -> None:
    assert connect(world.client, world.admin.headers, world.owner.tenant_id).status_code == 200
    world.execute("UPDATE whatsapp_connections SET status = 'error', last_error_code = '190'")
    world.chat("Hola")

    detail = world.admin_get(f"/admin/tenants/{world.owner.tenant_id}").json()

    whatsapp = detail["whatsapp_connection"]
    assert whatsapp["waba_masked"] == "•••• st-1" and whatsapp["waba_id"] is None
    assert whatsapp["admin_error"]["title"] == "El permiso de Meta venció"
    assert whatsapp["admin_error"]["meta_code"] == "190"
    assert detail["usage"] == {"conversations_this_month": 1, "allowance": 1000, "users": 1}
    assert detail["users"] == [
        {
            "id": str(world.owner.user_id),
            "name": world.owner.email,
            "email": world.owner.email,
            "role": "owner",
        }
    ]
    actions = [event["action"] for event in detail["activity"]]
    assert actions[-2:] == ["agent_config_saved", "sign_up"]
    assert "whatsapp_connected" in actions
    connected = next(e for e in detail["activity"] if e["action"] == "whatsapp_connected")
    assert (connected["actor_kind"], connected["actor_name"]) == ("admin", world.admin.email)
    assert [item["done"] for item in detail["onboarding"]] == [True, True, False, False, False]


def test_an_admin_creates_a_business_that_its_owner_claims(world: World, client, auth) -> None:
    created = world.admin_post(
        "/admin/tenants", {"business_name": "Palermo Propiedades", "owner_email": "Duenia@P.test"}
    )
    again = world.admin_post(
        "/admin/tenants", {"business_name": "Otra", "owner_email": "duenia@p.test"}
    )

    assert created.status_code == 201
    assert (created.json()["owner_email"], created.json()["owner_pending"]) == (
        "duenia@p.test",
        True,
    )
    assert (again.status_code, again.json()) == (409, {"code": "owner_email_taken"})

    user_id = uuid4()
    token = auth.register(user_id, email="duenia@p.test")
    joined = client.post(
        "/me/sign-up",
        json={"business_name": "Lo que escriba", "business_type": "inmobiliaria"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert joined.status_code == 201
    assert joined.json()["tenant"]["name"] == "Palermo Propiedades"
    detail = world.admin_get(f"/admin/tenants/{created.json()['id']}").json()
    assert detail["owner_pending"] is False
    assert [e["action"] for e in detail["activity"]] == ["owner_claimed", "tenant_created_by_admin"]


# --- Suspension --------------------------------------------------------------------------------


def test_a_suspended_business_keeps_its_data_but_nothing_runs(world: World) -> None:
    assert connect(world.client, world.admin.headers, world.owner.tenant_id).status_code == 200
    path = f"/admin/tenants/{world.owner.tenant_id}"

    suspended = world.admin_post(f"{path}/suspend", {"reason": "Pedido del cliente"})

    assert suspended.status_code == 200
    assert (suspended.json()["status"], suspended.json()["suspended_reason"]) == (
        "suspended",
        "Pedido del cliente",
    )
    for panel_path in ("/dashboard", "/leads", "/whatsapp", "/agent-setup"):
        response = world.owner.get(panel_path)
        assert (response.status_code, response.json()) == (403, {"code": "tenant_suspended"})
    me = world.owner.get("/me").json()
    assert me["tenant"]["status"] == "suspended" and me["support_email"]

    world.chat("Hola", "Quiero alquilar")

    # Stored for when it comes back; no agent reply, no read receipt, no email.
    assert [author for _, author, _ in world.transcript()] == ["visitor", "visitor"]
    assert world.graph.requests == []
    assert world.emails.sent == []

    world.admin_post(f"{path}/reactivate")
    world.chat("Hola de nuevo")

    assert world.owner.get("/dashboard").status_code == 200
    assert world.transcript()[-1][1] == "agent"
    assert world.graph.accepted >= 1
    actions = [e["action"] for e in world.admin_get(path).json()["activity"]]
    assert actions[:2] == ["tenant_reactivated", "tenant_suspended"]


def test_suspending_needs_a_reason(world: World) -> None:
    response = world.admin_post(f"/admin/tenants/{world.owner.tenant_id}/suspend", {"reason": ""})

    assert response.status_code == 422


# --- Salud del sistema and Planes --------------------------------------------------------------


def test_system_health_counts_jobs_webhooks_and_failed_sends(world: World) -> None:
    assert connect(world.client, world.admin.headers, world.owner.tenant_id).status_code == 200
    world.graph.fail_next = [(400, 131026)]
    world.chat("Hola")
    world.execute(
        "INSERT INTO jobs (id, kind, payload, run_at, status, attempts, max_attempts, "
        "created_at, finished_at) VALUES (gen_random_uuid(), 'x.dead', '{}', now(), 'dead', 8, "
        "8, now(), now())"
    )

    system = world.admin_get("/admin/system").json()

    assert system["database"] == "ok"
    assert system["webhooks_last_hour"] == 1
    assert system["failed_sends_last_24h"] == [{"code": "131026", "count": 1}]
    assert system["dead_last_24h"] == 1
    assert {"kind": "x.dead", "status": "dead", "count": 1} in system["jobs"]


def test_plans_list_the_tenants_on_each(world: World, client, auth) -> None:
    Account(client, auth, "Otra")
    world.execute("UPDATE tenants SET plan = 'pro' WHERE id = :t", t=world.owner.tenant_id)

    plans = world.admin_get("/admin/plans").json()

    assert plans == [
        {"plan": "trial", "name": "Prueba", "monthly_conversations": 1000, "tenants": 1},
        {"plan": "pro", "name": "Pro", "monthly_conversations": 1000, "tenants": 1},
    ]
