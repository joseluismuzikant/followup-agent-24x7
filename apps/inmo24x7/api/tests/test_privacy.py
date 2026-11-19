"""Privacy requests against the test database: "Eliminar datos de un contacto" and "Cerrar
cuenta y eliminar datos" from the backoffice.

The scans read every table of the database as text, so a table added later that keeps a
deleted contact's phone, thread or lead (or a closed business's id) fails here."""

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from inmo24x7_api.container import get_messaging_services
from inmo24x7_api.main import app
from test_inbox import _handed_off
from test_setup_endpoints import Account
from test_whatsapp import World, _world
from whatsapp_fakes import VISITOR

OTHER = "5493515550000"
# How the deleted contact's number can appear in a row.
VISITOR_FORMS = (VISITOR, "541155550188", "+54 9 11 5555-0188", "1155550188", "5555-0188")


@pytest.fixture
def world(client: TestClient, auth, database):
    yield _world(client, auth, database)
    app.dependency_overrides.pop(get_messaging_services, None)


def _admin(world: World, method: str, path: str, body: dict | None = None) -> Any:
    url = f"/admin/tenants/{world.owner.tenant_id}{path}"
    return world.client.request(method, url, json=body, headers=world.admin.headers)


def _tables(world: World) -> list[str]:
    return [
        row.tablename
        for row in world.sql(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
    ]


def _rows_containing(world: World, needles: list[str]) -> dict[str, list[str]]:
    """Every row of every table whose text holds one of the needles, by table."""
    found: dict[str, list[str]] = {}
    for table in _tables(world):
        for row in world.sql(f'SELECT t::text AS row FROM "{table}" t'):  # noqa: S608
            if any(needle in row.row for needle in needles):
                found.setdefault(table, []).append(row.row)
    return found


def _conversation_with_everything(world: World) -> dict[str, Any]:
    """A WhatsApp contact with a lead, a proposed visit, a condition event, a pending email
    job, model usage, an audited "no contactar" and the LangGraph checkpoints of its turns."""
    lead = _handed_off(world)
    thread = world.sql("SELECT id, key FROM conversation_threads WHERE visitor_id = :v", v=VISITOR)[
        0
    ]
    tenant = world.owner.tenant_id
    world.execute(
        "INSERT INTO lead_condition_events (id, tenant_id, lead_id, kind, dedupe, created_at) "
        "VALUES (:id, :t, :l, 'mismatch', 'x', now())",
        id=uuid4(),
        t=tenant,
        l=lead["id"],
    )
    world.execute(
        "INSERT INTO llm_usage (id, tenant_id, thread_id, channel, is_test, operation, provider,"
        " model, input_tokens, output_tokens, cached_input_tokens, usage_reported, latency_ms,"
        " succeeded, created_at) VALUES (:id, :t, :th, 'whatsapp', false, 'extract', 'fake',"
        " 'fake', 10, 5, 0, true, 100, true, now())",
        id=uuid4(),
        t=tenant,
        th=thread.id,
    )
    path = f"/leads/{lead['id']}/do-not-contact"
    assert world.owner.post(path, {"blocked": True}).status_code == 200
    assert world.sql("SELECT count(*) FROM checkpoints WHERE thread_id = :k", k=thread.key)[0][0]
    assert world.sql(
        "SELECT count(*) FROM jobs WHERE payload->>'lead_id' = :l AND status = 'queued'",
        l=lead["id"],
    )[0][0]
    return {"lead": lead, "thread_id": str(thread.id), "thread_key": thread.key}


# --- One contact ----------------------------------------------------------------------------


def test_contacts_are_found_by_phone_or_name(world: World) -> None:
    _handed_off(world)
    world.chat("Hola, busco alquilar en Córdoba", sender=OTHER)

    by_name = _admin(world, "GET", "/contacts?q=ana").json()
    by_phone = _admin(world, "GET", "/contacts?q=11 5555-0188").json()
    by_part = _admin(world, "GET", "/contacts?q=3515550000").json()

    assert [item["wa_id"] for item in by_name] == [VISITOR]
    (ana,) = by_phone
    assert ana["phone"] == "+54 9 11 5555-0188"
    assert ana["names"] == ["Ana Pérez"]
    assert (ana["leads"], ana["visits"], ana["do_not_contact"]) == (1, 1, False)
    assert ana["messages"] > 0
    assert [item["wa_id"] for item in by_part] == [OTHER]
    assert _admin(world, "GET", "/contacts?q=a").json() == []
    assert world.owner.get(f"/admin/tenants/{world.owner.tenant_id}/contacts").status_code == 403


def test_deleting_a_contact_leaves_nothing_of_it(world: World, client, auth) -> None:
    contact = _conversation_with_everything(world)
    world.chat("Hola, busco alquilar en Córdoba", sender=OTHER)
    other_business = Account(client, auth, "Otra Inmobiliaria")
    other_business.post("/simulator/messages", {"text": "Hola, busco en Belgrano"})
    before_other = _rows_containing(world, [str(other_business.tenant_id)])
    other_contact = world.sql(
        "SELECT count(*) FROM conversation_messages m JOIN conversation_threads t "
        "ON t.id = m.thread_id WHERE t.visitor_id = :v",
        v=OTHER,
    )[0][0]

    wrong = _admin(world, "POST", "/contacts/delete", {"wa_id": VISITOR, "confirmation": "11"})
    assert (wrong.status_code, wrong.json()["code"]) == (422, "confirmation_mismatch")
    deleted = _admin(
        world, "POST", "/contacts/delete", {"wa_id": VISITOR, "confirmation": "11 5555-0188"}
    )

    assert deleted.status_code == 200
    counts = deleted.json()
    assert (counts["leads"], counts["conversations"], counts["visits"]) == (1, 1, 1)
    assert counts["messages"] > 0
    needles = [*VISITOR_FORMS, contact["thread_id"], contact["thread_key"], contact["lead"]["id"]]
    leftovers = _rows_containing(world, needles)
    # Only the "BAJA" survives, so it keeps being honored.
    assert set(leftovers) == {"do_not_contact"}
    flag = world.sql("SELECT * FROM do_not_contact WHERE tenant_id = :t", t=world.owner.tenant_id)
    assert [(row.wa_id, row.source_message_id, row.confirmation_message_id) for row in flag] == [
        (VISITOR, None, None)
    ]
    # Model usage stays for the cost totals, unlinked.
    assert (
        world.sql(
            "SELECT count(*) FROM llm_usage WHERE thread_id IS NULL AND tenant_id = :t",
            t=world.owner.tenant_id,
        )[0][0]
        == 1
    )
    (event,) = world.sql(
        "SELECT actor_kind, actor_profile_id, details FROM audit_events "
        "WHERE action = 'contact_data_deleted'"
    )
    assert (event.actor_kind, event.actor_profile_id) == ("admin", world.admin.user_id)
    assert event.details["leads"] == 1 and set(event.details) == {
        "leads",
        "threads",
        "messages",
        "visits",
        "llm_calls_unlinked",
    }
    # The other contact and the other business are untouched.
    assert (
        world.sql(
            "SELECT count(*) FROM conversation_messages m JOIN conversation_threads t "
            "ON t.id = m.thread_id WHERE t.visitor_id = :v",
            v=OTHER,
        )[0][0]
        == other_contact
    )
    assert _rows_containing(world, [str(other_business.tenant_id)]) == before_other
    again = _admin(
        world, "POST", "/contacts/delete", {"wa_id": VISITOR, "confirmation": "11 5555-0188"}
    )
    assert (again.status_code, again.json()["code"]) == (404, "contact_not_found")


def test_a_baja_is_still_honored_after_deleting_the_contact(world: World) -> None:
    world.chat("Hola, busco alquilar en Palermo", "BAJA")
    _admin(world, "POST", "/contacts/delete", {"wa_id": VISITOR, "confirmation": VISITOR})
    sent = len(world.graph.sent())

    world.chat("baja")

    assert len(world.graph.sent()) == sent  # still opted out: no second confirmation


# --- A whole business -----------------------------------------------------------------------


def _users_with_logins(world: World) -> tuple[str, str]:
    """The owner (only in this business) and a teammate who also uses Cuentas Claras."""
    teammate = uuid4()
    other_tenant = uuid4()
    world.execute(
        "INSERT INTO tenants (id, product, name, slug, created_at, status, trial_ends_at, plan) "
        "VALUES (:id, 'cuentas_claras', 'Ascensores', :slug, now(), 'active', now(), 'trial')",
        id=other_tenant,
        slug=f"asc-{other_tenant.hex}",
    )
    for tenant, product in ((world.owner.tenant_id, "inmo24x7"), (other_tenant, "cuentas_claras")):
        world.execute(
            "INSERT INTO profiles (id, email, display_name, tenant_id, role, is_platform_admin,"
            " created_at, product, user_id) VALUES (:id, 'socio@example.com', 'Socio', :t,"
            " 'agent', false, now(), :p, :u)",
            id=uuid4(),
            t=tenant,
            p=product,
            u=teammate,
        )
    owner_email = world.owner.email
    for user, email in ((world.owner.user_id, owner_email), (teammate, "socio@example.com")):
        world.execute(
            "INSERT INTO accounts (user_id, email, must_change_password, created_at) "
            "VALUES (:u, :e, false, now())",
            u=user,
            e=email,
        )
        world.execute("INSERT INTO dev_passwords (email, password_hash) VALUES (:e, 'x')", e=email)
    return owner_email, "socio@example.com"


def test_closing_needs_the_business_name_and_stops_it_at_once(world: World) -> None:
    summary = _admin(world, "GET", "/closure").json()
    assert summary["name"] == "Inmobiliaria Sur" and summary["closing"] is False

    wrong = _admin(world, "POST", "/close", {"business_name": "Otra"})
    assert (wrong.status_code, wrong.json()["code"]) == (422, "confirmation_mismatch")
    accepted = _admin(world, "POST", "/close", {"business_name": "inmobiliaria sur "})

    assert accepted.status_code == 202 and accepted.json()["closing"] is True
    detail = world.client.get(
        f"/admin/tenants/{world.owner.tenant_id}", headers=world.admin.headers
    ).json()
    assert (detail["status"], detail["closing"]) == ("suspended", True)
    reactivate = _admin(world, "POST", "/reactivate")
    assert (reactivate.status_code, reactivate.json()["code"]) == (409, "account_closing")
    platform = world.client.post(
        f"/admin/tenants/{world.admin.tenant_id}/close",
        json={"business_name": "Plataforma"},
        headers=world.admin.headers,
    )
    assert platform.status_code in (404, 409)


def test_closing_deletes_every_row_of_the_business(world: World, client, auth) -> None:
    _conversation_with_everything(world)
    world.chat("Hola, busco alquilar en Córdoba", sender=OTHER)
    world.owner.post("/simulator/messages", {"text": "Hola"})
    owner_email, teammate_email = _users_with_logins(world)
    other_business = Account(client, auth, "Otra Inmobiliaria")
    other_business.post("/simulator/messages", {"text": "Hola, busco en Belgrano"})
    before_other = _rows_containing(world, [str(other_business.tenant_id)])
    tenant = str(world.owner.tenant_id)

    assert _admin(world, "POST", "/close", {"business_name": "Inmobiliaria Sur"}).status_code == 202
    world.run()
    world.run(after_seconds=120)  # the cleanup job forgets the finished closing job

    leftovers = _rows_containing(world, [tenant])
    assert set(leftovers) == {"tenants", "audit_events", "llm_usage"}
    (tombstone,) = world.sql(
        "SELECT name, slug, status, suspended_reason FROM tenants WHERE id = :t", t=tenant
    )
    assert (tombstone.name, tombstone.status, tombstone.suspended_reason) == (
        "Cuenta eliminada",
        "deleted",
        None,
    )
    (closed,) = world.sql(
        "SELECT action, actor_profile_id, details FROM audit_events WHERE tenant_id = :t",
        t=tenant,
    )
    assert (closed.action, closed.actor_profile_id) == ("account_closed", world.admin.user_id)
    assert closed.details["code"] == "meta_unsubscribed"
    assert closed.details["users"] == 2 and closed.details["users_kept"] == 1
    assert all(
        row.thread_id is None
        for row in world.sql("SELECT thread_id FROM llm_usage WHERE tenant_id = :t", t=tenant)
    )
    # Nothing personal anywhere: names, emails, phones, the business name.
    assert _rows_containing(world, ["Inmobiliaria Sur", "Ana Pérez", owner_email]) == {}
    assert _rows_containing(world, list(VISITOR_FORMS)) == {}
    # Our app left the WABA; nothing else at Meta was touched.
    deletes = [path for method, path, _body in world.graph.requests if method == "DELETE"]
    assert len(deletes) == 1 and deletes[0].endswith("/waba-test-1/subscribed_apps")
    # The teammate keeps their login for Cuentas Claras; the owner's is gone.
    assert [row.email for row in world.sql("SELECT email FROM accounts")] == [teammate_email]
    assert [row.email for row in world.sql("SELECT email FROM dev_passwords")] == [teammate_email]
    # Another business is untouched, and the closed one is gone from the backoffice.
    assert _rows_containing(world, [str(other_business.tenant_id)]) == before_other
    assert _admin(world, "GET", "").status_code == 404
    listed = world.client.get("/admin/tenants", headers=world.admin.headers).json()["items"]
    assert tenant not in [item["id"] for item in listed]
    # The former owner has no profile any more.
    gone = world.owner.get("/leads")
    assert (gone.status_code, gone.json()["code"]) == (404, "profile_not_found")


def test_the_closing_job_survives_a_meta_failure_and_runs_once(world: World) -> None:
    world.graph.fail_on["/subscribed_apps"] = [(400, 190)]  # token revoked

    _admin(world, "POST", "/close", {"business_name": "Inmobiliaria Sur"})
    world.run()
    world.run()

    (closed,) = world.sql(
        "SELECT details FROM audit_events WHERE tenant_id = :t", t=world.owner.tenant_id
    )
    assert closed.details["code"] == "meta_unsubscribe_failed"
    assert world.jobs("tenant.close") == [("done", 1)]
    world.run(after_seconds=120)
    assert world.jobs("tenant.close") == []
    assert world.jobs("tenant.close_cleanup") == [("done", 1)]
