"""Integrations end to end against the test database: Tokko Broker (connect, sync, re-sync,
leads out), the lead webhook (signature, retries, delivery log, test ping) and the website
button's public configuration. Tokko, the webhook receiver, Meta and the model are fakes."""

import hashlib
import hmac
from typing import Any

import pytest
from fastapi.testclient import TestClient
from inmo24x7_api.container import get_messaging_services
from inmo24x7_api.main import app
from integration_fakes import (
    TOKKO_KEY,
    WEBHOOK_URL,
    FakeReceiver,
    FakeTokko,
    fake_integrations,
    rent,
    sale,
    tokko_property,
)
from test_inbox import _handed_off
from test_whatsapp import World, _world
from whatsapp_fakes import VISITOR


@pytest.fixture
def world(client: TestClient, auth, database, monkeypatch):
    with fake_integrations(monkeypatch) as (tokko, receiver):
        built = _world(client, auth, database)
        built.tokko = tokko  # type: ignore[attr-defined]
        built.receiver = receiver  # type: ignore[attr-defined]
        yield built
    app.dependency_overrides.pop(get_messaging_services, None)


def _tokko(world: World) -> FakeTokko:
    return world.tokko  # type: ignore[attr-defined]


def _receiver(world: World) -> FakeReceiver:
    return world.receiver  # type: ignore[attr-defined]


def _call(world: World, method: str, path: str, body: dict | None = None):
    return world.client.request(method, path, json=body, headers=world.owner.headers)


def _connect(world: World) -> dict:
    response = _call(world, "PUT", "/integrations/tokko", {"api_key": TOKKO_KEY})
    assert response.status_code == 200, response.json()
    return response.json()


def _properties(world: World) -> list[dict[str, Any]]:
    return sorted(
        world.owner.get("/properties").json()["items"],
        key=lambda item: (item["external_id"] or "", item["operation"]),
    )


# --- Tokko: connect and import ----------------------------------------------------------------


def test_a_wrong_key_is_not_saved_and_the_right_one_is_stored_encrypted(world: World) -> None:
    wrong = _call(world, "PUT", "/integrations/tokko", {"api_key": "wrong-key-123"})
    assert (wrong.status_code, wrong.json()["code"]) == (422, "tokko_key_invalid")
    assert world.sql("SELECT count(*) FROM inmo_integrations WHERE provider = 'tokko'")[0][0] == 0

    body = _connect(world)

    assert body["tokko"]["connected"] is True
    assert body["tokko"]["last_sync_status"] == "queued"
    (stored,) = world.sql("SELECT credentials FROM inmo_integrations WHERE provider = 'tokko'")
    assert stored.credentials.startswith("k1:") and TOKKO_KEY not in stored.credentials
    # The key never goes back to the browser, nor into the audit log.
    assert TOKKO_KEY not in world.owner.get("/integrations").text
    assert all(TOKKO_KEY not in str(row) for row in world.sql("SELECT * FROM audit_events"))
    # "Probar conexión" is one read.
    assert [(m, p) for m, p, _ in _tokko(world).requests][-1] == ("GET", "/api/v1/property/")


def test_the_sync_maps_listings_one_per_operation_and_reports_failures(world: World) -> None:
    tokko = _tokko(world)
    tokko.properties = [
        tokko_property(101),
        tokko_property(
            102,
            title="3 ambientes con balcón",
            address="Cabildo 2100",
            zone="Belgrano",
            rooms=3,
            operations=[sale(185000), rent(1200000)],
        ),
        tokko_property(103, title="Sin precio", operations=[{"operation_type": "Venta"}]),
        tokko_property(104, title="Sin ambientes", rooms=None, operations=[rent()]),
    ]
    tokko.properties[3]["suite_amount"] = None
    _connect(world)

    world.run()

    items = _properties(world)
    assert [(i["external_id"], i["operation"], i["price"], i["currency"]) for i in items] == [
        ("101", "rent", 850000, "ARS"),
        ("102", "rent", 1200000, "ARS"),
        ("102", "sale", 185000, "USD"),
    ]
    first = items[0]
    assert (first["source"], first["external_ref"], first["zone"], first["rooms"]) == (
        "tokko",
        "TKO101",
        "Palermo",
        2,
    )
    assert first["link"] == "https://www.inmosur.com.ar/propiedad/101"
    report = world.owner.get("/integrations").json()["tokko"]
    assert report["last_sync_status"] == "ok"
    assert (report["last_report"]["created"], report["last_report"]["paused"]) == (3, 0)
    assert [(f["external_id"], f["reason"]) for f in report["last_report"]["failed"]] == [
        ("103", "la venta no tiene precio publicado."),
        ("104", "no tiene la cantidad de ambientes."),
    ]
    # Paginated: every page was read.
    offsets = [p.get("offset") for m, path, p in tokko.requests if p.get("limit") == "50"]
    assert offsets == ["0", "2"]


def test_a_resync_updates_in_place_pauses_what_is_gone_and_keeps_our_conditions(
    world: World,
) -> None:
    tokko = _tokko(world)
    tokko.properties = [tokko_property(101), tokko_property(102, address="Cabildo 2100")]
    _connect(world)
    world.run()
    gorriti, cabildo = _properties(world)
    conditions = {"conditions": {"garantias": ["caucion"], "mascotas": True}}
    assert _call(world, "PATCH", f"/properties/{gorriti['id']}", conditions).status_code == 200
    # Tokko's fields are edited in Tokko.
    title = _call(world, "PATCH", f"/properties/{gorriti['id']}", {"title": "Otro"})
    assert (title.status_code, title.json()["code"]) == (409, "property_managed_by_tokko")
    pause = _call(world, "POST", f"/properties/{gorriti['id']}/pause")
    assert (pause.status_code, pause.json()["code"]) == (409, "property_managed_by_tokko")

    tokko.properties = [tokko_property(101, operations=[rent(900000)])]
    assert _call(world, "POST", "/integrations/tokko/sync").status_code == 202
    world.run()

    gorriti_now, cabildo_now = _properties(world)
    assert gorriti_now["id"] == gorriti["id"] and gorriti_now["price"] == 900000
    assert gorriti_now["conditions"]["garantias"] == ["caucion"]
    assert gorriti_now["conditions"]["mascotas"] is True
    # Gone from Tokko: paused here, never deleted.
    assert (cabildo_now["id"], cabildo_now["status"]) == (cabildo["id"], "paused")
    report = world.owner.get("/integrations").json()["tokko"]["last_report"]
    assert (report["created"], report["updated"], report["paused"]) == (0, 1, 1)

    # Back in Tokko: published again.
    tokko.properties.append(tokko_property(102, address="Cabildo 2100"))
    _call(world, "POST", "/integrations/tokko/sync")
    world.run(after_seconds=61)
    assert [item["status"] for item in _properties(world)] == ["published", "published"]


def test_a_failed_sync_pauses_nothing(world: World) -> None:
    tokko = _tokko(world)
    tokko.properties = [tokko_property(101)]
    _connect(world)
    world.run()
    tokko.down = True

    _call(world, "POST", "/integrations/tokko/sync")
    world.run()

    assert [item["status"] for item in _properties(world)] == ["published"]
    status = world.owner.get("/integrations").json()["tokko"]
    assert (status["last_sync_status"], status["last_error_code"]) == (
        "failed",
        "tokko_unavailable",
    )


def test_the_sweep_queues_one_sync_per_agency_every_six_hours(world: World) -> None:
    from datetime import UTC, datetime

    from inmo24x7_api.integrations.application import sync_sweep_job
    from inmo24x7_api.integrations.repositories import SqlAlchemyIntegrationRepository  # noqa

    _tokko(world).properties = [tokko_property(101)]
    _connect(world)
    world.run()
    with world.sessions() as session:
        from followup_core.scheduling.infrastructure.queue import SqlAlchemyJobQueue

        queue = SqlAlchemyJobQueue(session, queue="inmo24x7")
        assert queue.enqueue(sync_sweep_job(datetime.now(UTC)))
        assert not queue.enqueue(sync_sweep_job(datetime.now(UTC)))  # one per slot
        session.commit()

    world.run()

    assert world.jobs("integrations.tokko_sync") == [("done", 1), ("done", 1)]
    sweeps = world.jobs("integrations.tokko_sync_sweep")
    assert sorted(sweeps) == [("done", 1), ("queued", 0)]  # and the next one, 6 hours later


# --- Leads out ---------------------------------------------------------------------------------


def _webhook(world: World) -> str:
    response = _call(world, "PUT", "/integrations/webhook", {"url": WEBHOOK_URL})
    assert response.status_code == 200, response.json()
    secret = response.json()["secret"]
    assert secret and secret.startswith("whsec_")
    return secret


def _verify(secret: str, request) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), request.content, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, request.headers["X-Inmo24x7-Signature"])


def test_a_handed_off_lead_goes_to_tokko_and_the_webhook_once(world: World) -> None:
    tokko = _tokko(world)
    tokko.properties = [tokko_property(101)]
    _connect(world)
    world.run()
    secret = _webhook(world)

    lead = _handed_off(world)
    world.run()
    world.run()

    (contact,) = tokko.contacts
    assert contact["name"] == "Ana Pérez"
    assert contact["cellphone"] == "+54 9 11 5555-0188"
    assert contact["properties"] == [101]
    assert contact["tags"] == ["inmo24x7"]
    assert contact["text"].startswith("Busca alquiler en Palermo.")
    assert "Pidió visita " in contact["text"] and contact["text"].endswith("— vía inmo24x7")

    (request,) = _receiver(world).received
    assert _verify(secret, request)
    assert request.headers["X-Inmo24x7-Event"] == "lead.handed_off"
    (body,) = _receiver(world).bodies()
    assert body["delivery_id"] == request.headers["X-Inmo24x7-Delivery"]
    sent = body["lead"]
    assert (sent["id"], sent["name"], sent["operation"], sent["zone"]) == (
        lead["id"],
        "Ana Pérez",
        "rent",
        "Palermo",
    )
    (chosen,) = sent["properties"]
    assert (chosen["source"], chosen["external_id"], chosen["external_ref"]) == (
        "tokko",
        "101",
        "TKO101",
    )
    assert sent["visit"]["status"] == "proposed"
    assert sent["panel_link"] == f"https://panel.example.com/consultas?lead={lead['id']}"

    deliveries = world.owner.get(f"/leads/{lead['id']}/deliveries").json()
    assert sorted((d["provider"], d["status"]) for d in deliveries) == [
        ("tokko", "delivered"),
        ("webhook", "delivered"),
    ]
    # More turns after the hand-off never deliver again.
    world.chat("Gracias!")
    world.run()
    assert len(tokko.contacts) == 1 and len(_receiver(world).received) == 1


def test_a_failing_webhook_is_retried_with_backoff_and_a_400_is_final(world: World) -> None:
    _webhook(world)
    receiver = _receiver(world)
    receiver.statuses = [503, 200]

    lead = _handed_off(world)
    (first,) = world.owner.get(f"/leads/{lead['id']}/deliveries").json()
    assert (first["status"], first["status_code"], first["attempts"]) == ("retrying", 503, 1)

    world.run(after_seconds=30)

    (done,) = world.owner.get(f"/leads/{lead['id']}/deliveries").json()
    assert (done["status"], done["status_code"], done["attempts"]) == ("delivered", 200, 2)
    # The same delivery id on both attempts, so the receiver can drop duplicates.
    ids = {request.headers["X-Inmo24x7-Delivery"] for request in receiver.received}
    assert len(receiver.received) == 2 and len(ids) == 1

    receiver.statuses = [400]
    test = _call(world, "POST", "/integrations/webhook/test")
    assert (test.json()["status"], test.json()["status_code"]) == ("failed", 400)
    log = world.owner.get("/integrations").json()["webhook"]["deliveries"]
    # (The worker's test clock runs ahead of the API's, so compare without the order.)
    assert sorted((d["event"], d["status"]) for d in log) == [
        ("lead.handed_off", "delivered"),
        ("ping", "failed"),
    ]


def test_a_rejected_tokko_contact_is_not_retried(world: World) -> None:
    tokko = _tokko(world)
    _connect(world)
    world.run()
    tokko.contact_failures = [400]

    lead = _handed_off(world)
    world.run()
    world.run(after_seconds=60)

    (delivery,) = world.owner.get(f"/leads/{lead['id']}/deliveries").json()
    assert (delivery["status"], delivery["error_code"], delivery["attempts"]) == (
        "failed",
        "tokko_contact_rejected",
        1,
    )
    assert world.jobs("integrations.deliver_lead") == [("done", 1)]


def test_a_lead_who_said_baja_is_still_delivered_marked(world: World) -> None:
    _webhook(world)
    _receiver(world).statuses = [503]  # the first attempt fails: retried after the "BAJA"
    lead = _handed_off(world)
    blocked = _call(world, "POST", f"/leads/{lead['id']}/do-not-contact", {"blocked": True})
    assert blocked.status_code == 200

    world.run(after_seconds=30)

    retried = _receiver(world).bodies()[-1]
    assert retried["lead"]["do_not_contact"] is True
    assert "Pidió no ser contactado" in retried["lead"]["summary"]


def test_sending_leads_can_be_turned_off(world: World) -> None:
    tokko = _tokko(world)
    _connect(world)
    world.run()
    options = {"import_properties": True, "send_leads": False}
    assert _call(world, "PATCH", "/integrations/tokko", options).status_code == 200

    _handed_off(world)
    world.run()

    assert tokko.contacts == []


# --- Webhook settings and the button -----------------------------------------------------------


def test_the_webhook_needs_https_and_its_secret_is_shown_once(world: World) -> None:
    bad = _call(world, "PUT", "/integrations/webhook", {"url": "http://crm.example.com/x"})
    assert (bad.status_code, bad.json()["code"]) == (422, "webhook_url_invalid")
    secret = _webhook(world)

    again = _call(world, "PUT", "/integrations/webhook", {"url": WEBHOOK_URL, "enabled": True})
    assert again.json()["secret"] is None
    assert secret not in world.owner.get("/integrations").text
    rotated = _call(world, "POST", "/integrations/webhook/secret").json()["secret"]
    assert rotated and rotated != secret

    ping = _call(world, "POST", "/integrations/webhook/test").json()
    assert ping["status"] == "delivered"
    assert _verify(rotated, _receiver(world).received[-1])


def test_the_button_config_is_public_and_only_public(world: World) -> None:
    widget = world.owner.get("/integrations").json()["widget"]
    saved = _call(
        world,
        "PUT",
        "/integrations/widget",
        {
            "enabled": True,
            "color": "#1E3A8A",
            "text_color": "#FFFFFF",
            "position": "left",
            "label": "Escribinos",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["widget"]["public_id"] == widget["public_id"]

    public = world.client.get(
        f"/widget/v1/{widget['public_id']}", headers={"Origin": "https://www.inmosur.com.ar"}
    )

    assert public.status_code == 200
    assert public.headers["access-control-allow-origin"] == "*"
    assert set(public.json()) == {
        "agency_name",
        "phone",
        "color",
        "text_color",
        "position",
        "label",
    }
    assert public.json()["color"] == "#1e3a8a" and public.json()["position"] == "left"
    assert public.json()["agency_name"] == "Inmobiliaria Sur"
    assert world.client.get("/widget/v1/nope-nope").status_code == 404
    assert world.client.post(f"/widget/v1/{widget['public_id']}").status_code == 405
    invalid = _call(
        world, "PUT", "/integrations/widget", {"color": "red", "text_color": "#fff", "label": "x"}
    )
    assert invalid.status_code == 422


def test_a_lead_from_the_button_is_marked_web(world: World) -> None:
    _tokko(world).properties = [tokko_property(101)]
    _connect(world)
    world.run()

    world.chat("Hola, me interesa la propiedad «2 ambientes luminoso» (ref. TKO101)")

    (lead,) = world.owner.get("/leads").json()["items"]
    assert lead["source"] == "web_button"
    sent = [b for b in world.graph.sent() if b.get("type") == "interactive"]
    assert sent, "the visit times of the named property are offered right away"


# --- Deletion (PR #17's privacy requests) ------------------------------------------------------


def _everything_integrated(world: World) -> dict:
    """Tokko connected and synced, a webhook, the button, and a lead delivered to both."""
    _tokko(world).properties = [tokko_property(101)]
    _connect(world)
    world.run()
    _webhook(world)
    world.owner.get("/integrations")  # the button's row
    lead = _handed_off(world)
    world.run()
    assert len(world.owner.get(f"/leads/{lead['id']}/deliveries").json()) == 2
    return lead


def test_deleting_a_contact_deletes_its_delivery_logs(world: World) -> None:
    from test_privacy import VISITOR_FORMS, _admin, _rows_containing

    lead = _everything_integrated(world)

    deleted = _admin(
        world, "POST", "/contacts/delete", {"wa_id": VISITOR, "confirmation": "11 5555-0188"}
    )

    assert deleted.status_code == 200
    assert _rows_containing(world, [*VISITOR_FORMS, lead["id"]]) == {}
    assert world.sql("SELECT count(*) FROM inmo_lead_deliveries")[0][0] == 0
    # The agency's integrations stay.
    assert world.sql("SELECT count(*) FROM inmo_integrations")[0][0] == 3


def test_closing_the_agency_deletes_its_integrations_and_credentials(world: World) -> None:
    from test_privacy import _admin, _rows_containing

    _everything_integrated(world)
    _call(world, "POST", "/integrations/webhook/test")
    tenant = str(world.owner.tenant_id)

    closed = _admin(world, "POST", "/close", {"business_name": "Inmobiliaria Sur"})
    assert closed.status_code == 202
    world.run()
    world.run(after_seconds=120)

    assert set(_rows_containing(world, [tenant])) <= {"tenants", "audit_events", "llm_usage"}
    for table in ("inmo_integrations", "inmo_sync_reports", "inmo_lead_deliveries"):
        assert world.sql(f"SELECT count(*) FROM {table}")[0][0] == 0  # noqa: S608
