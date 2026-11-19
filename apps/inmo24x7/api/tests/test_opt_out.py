""" "BAJA" end to end: the webhook, the agent turn and the send job against the test database.
Meta is the fake Graph API and the model the fake one; nothing leaves the machine.

What must hold: one confirmation and then silence; nothing else reaches the contact
(templates, team replies, messages queued before the "BAJA"); writing again with a new
inquiry lifts it; another business can still talk to the same number; "planta baja" is
never an opt-out."""

import pytest
from fastapi.testclient import TestClient
from followup_core.messaging.domain.opt_out import OPT_OUT_CONFIRMATION
from inmo24x7_api.container import get_messaging_services
from inmo24x7_api.main import app
from test_inbox import _detail, _handed_off, _simulator_lead, _take_over
from test_setup_endpoints import Account, _body, _set_role
from test_whatsapp import World, _world
from whatsapp_fakes import VISITOR, connect, simulate_whatsapp


@pytest.fixture
def world(client: TestClient, auth, database):
    yield _world(client, auth, database)
    app.dependency_overrides.pop(get_messaging_services, None)


def _texts(world: World) -> list[str]:
    return [body["text"]["body"] for body in world.graph.sent() if body.get("type") == "text"]


def _flag(world: World, tenant_id=None) -> list[tuple[str, str]]:
    return [
        (row.wa_id, row.source)
        for row in world.sql(
            "SELECT wa_id, source FROM do_not_contact WHERE tenant_id = :t",
            t=tenant_id or world.owner.tenant_id,
        )
    ]


def _audit(world: World) -> list[tuple[str, dict]]:
    return [
        (row.action, row.details)
        for row in world.sql(
            "SELECT action, details FROM audit_events WHERE tenant_id = :t "
            "AND action LIKE 'contact_opt%' ORDER BY at",
            t=world.owner.tenant_id,
        )
    ]


def _lead(world: World) -> dict:
    (lead,) = world.owner.get("/leads").json()["items"]
    return lead


def test_baja_sends_one_confirmation_and_then_silence(world: World) -> None:
    world.chat("Hola, busco alquilar un 2 ambientes en Palermo")
    before = len(world.graph.sent())

    world.chat("BAJA")

    assert world.graph.sent()[before:] == [
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "541155550188",
            "type": "text",
            "text": {"body": OPT_OUT_CONFIRMATION, "preview_url": False},
        }
    ]
    assert _flag(world) == [(VISITOR, "message")]
    assert _audit(world) == [("contact_opted_out", {"source": "message"})]
    lead = _lead(world)
    assert lead["do_not_contact"] is True
    # The team gets the usual lead email, marked.
    (email,) = [e for e in world.emails.sent if e.subject.startswith("Pidió no ser contactado")]
    assert "«BAJA»" in email.text

    world.chat("No me escriban más!!")

    assert len(world.graph.sent()) == before + 1  # no second confirmation, no reply
    assert world.transcript()[-1] == ("inbound", "visitor", "No me escriban más!!")
    assert len(_audit(world)) == 1


def test_planta_baja_is_a_question_not_an_opt_out(world: World) -> None:
    world.chat("Hola, busco alquilar un 2 ambientes en Palermo")
    before = len(world.graph.sent())

    world.chat("¿La planta baja está disponible?")

    assert len(world.graph.sent()) > before
    assert OPT_OUT_CONFIRMATION not in _texts(world)
    assert _flag(world) == []


def test_the_extractor_catches_other_words(world: World) -> None:
    world.chat("Hola, busco alquilar un 2 ambientes en Palermo")

    world.chat("Por favor no me molesten más")

    assert _texts(world)[-1] == OPT_OUT_CONFIRMATION
    assert _flag(world) == [(VISITOR, "message")]
    assert _lead(world)["do_not_contact"] is True


def test_nothing_else_reaches_the_contact(world: World) -> None:
    lead = _handed_off(world)
    (visit,) = _detail(world, lead["id"])["visits"]
    assert _take_over(world, lead["id"]).status_code == 200
    sent = len(_texts(world))

    # Taken over by the team: the confirmation goes anyway.
    world.chat("baja")

    assert _texts(world)[sent:] == [OPT_OUT_CONFIRMATION]
    for path, body in (
        (f"/leads/{lead['id']}/messages", {"text": "¿Seguro?"}),
        (f"/leads/{lead['id']}/visits/{visit['id']}/confirm", {}),
        (f"/leads/{lead['id']}/visits/{visit['id']}/cancel", {"message": "Se cancela"}),
    ):
        refused = world.owner.post(path, body)
        assert (refused.status_code, refused.json()["code"]) == (409, "contact_opted_out"), path
    # Cancelling without a message sends nothing, so it stays possible.
    cancel = f"/leads/{lead['id']}/visits/{visit['id']}/cancel"
    assert world.owner.post(cancel, {}).status_code == 200
    world.run()
    assert _texts(world)[sent:] == [OPT_OUT_CONFIRMATION]


def test_a_template_queued_for_a_contact_who_opted_out_is_not_sent(world: World) -> None:
    lead = _handed_off(world)
    (visit,) = _detail(world, lead["id"])["visits"]
    connect(
        world.client,
        world.admin.headers,
        world.owner.tenant_id,
        visit_template_name="confirmacion_visita",
    )
    world.execute(
        "UPDATE conversation_messages SET created_at = created_at - interval '2 days' "
        "WHERE author = 'visitor'"
    )
    confirmed = world.owner.post(f"/leads/{lead['id']}/visits/{visit['id']}/confirm", {})
    assert confirmed.status_code == 200
    # The "BAJA" arrives by phone before the send job runs: the team marks it.
    assert (
        world.owner.post(f"/leads/{lead['id']}/do-not-contact", {"blocked": True}).status_code
        == 200
    )
    sent = len(world.graph.sent())

    world.run()

    assert len(world.graph.sent()) == sent
    assert world.outbound()[-1] == ("failed", None, "do_not_contact")


def test_writing_again_with_a_new_inquiry_lifts_it(world: World) -> None:
    world.chat("Hola, busco alquilar un 2 ambientes en Palermo", "BAJA")
    before = len(world.graph.sent())

    world.chat("Hola de nuevo, ¿siguen teniendo opciones en Palermo?")

    assert _flag(world) == []
    assert len(world.graph.sent()) > before
    assert _audit(world)[-1] == ("contact_opt_out_lifted", {"source": "message"})
    assert _lead(world)["do_not_contact"] is False


def test_another_business_can_still_talk_to_the_same_number(
    world: World, client: TestClient, auth
) -> None:
    other = Account(client, auth, "Otra Inmobiliaria")
    setup = other.get("/agent-setup").json()
    always = [{"weekday": day, "opens": "00:00", "closes": "23:30"} for day in range(7)]
    other.put("/agent-setup", _body(setup, business_hours=always))
    assert (
        connect(
            client, world.admin.headers, other.tenant_id, phone_number_id="pn-test-2"
        ).status_code
        == 200
    )
    world.chat("Hola, busco alquilar en Palermo", "BAJA")
    before = len(world.graph.sent())

    payload = simulate_whatsapp.message_payload(
        "Hola, busco alquilar en Belgrano", sender=VISITOR, phone_number_id="pn-test-2"
    )
    assert world.post(payload) == 200
    world.run()

    assert len(world.graph.sent()) > before
    assert OPT_OUT_CONFIRMATION not in _texts(world)[before:]
    assert _flag(world, other.tenant_id) == []
    assert _flag(world) == [(VISITOR, "message")]


def test_the_team_marks_and_removes_it_and_both_are_audited(world: World, db_session) -> None:
    world.chat("Hola, busco alquilar un 2 ambientes en Palermo")
    lead = _lead(world)
    path = f"/leads/{lead['id']}/do-not-contact"

    marked = world.owner.post(path, {"blocked": True}).json()
    assert marked["do_not_contact"] is True
    assert _flag(world) == [(VISITOR, "team")]
    removed = world.owner.post(path, {"blocked": False}).json()
    assert removed["do_not_contact"] is False

    assert _audit(world) == [
        ("contact_opted_out", {"source": "team", "lead_id": lead["id"]}),
        ("contact_opt_out_lifted", {"source": "team", "lead_id": lead["id"]}),
    ]
    _set_role(db_session, world.owner.user_id, "viewer")
    assert world.owner.post(path, {"blocked": True}).status_code == 403


def test_a_simulator_lead_has_no_whatsapp_contact_to_mark(world: World) -> None:
    lead = _simulator_lead(world.owner)

    refused = world.owner.post(f"/leads/{lead['id']}/do-not-contact", {"blocked": True})

    assert (refused.status_code, refused.json()["code"]) == (409, "lead_not_whatsapp")


def test_the_simulator_shows_the_confirmation(world: World) -> None:
    world.owner.post("/simulator/messages", {"text": "Hola, busco alquilar en Palermo"})

    reply = world.owner.post("/simulator/messages", {"text": "Dejen de escribirme"}).json()

    assert [message["text"] for message in reply["messages"]] == [OPT_OUT_CONFIRMATION]


def test_an_admin_marks_a_number_that_never_wrote(world: World) -> None:
    path = f"/admin/tenants/{world.owner.tenant_id}/do-not-contact"

    marked = world.client.post(
        path, json={"phone": "11 4444-0000", "blocked": True}, headers=world.admin.headers
    ).json()

    assert marked == {
        "wa_id": "5491144440000",
        "phone": "+54 9 11 4444-0000",
        "do_not_contact": True,
    }
    assert _flag(world) == [("5491144440000", "admin")]
    # Not even the connection's test template.
    test = world.client.post(
        f"/admin/tenants/{world.owner.tenant_id}/whatsapp/test-message",
        json={"to": "+54 9 11 4444-0000"},
        headers=world.admin.headers,
    )
    assert (test.status_code, test.json()["code"]) == (409, "contact_opted_out")
    invalid = world.client.post(
        path, json={"phone": "123456", "blocked": True}, headers=world.admin.headers
    )
    assert (invalid.status_code, invalid.json()["code"]) == (422, "phone_invalid")
    assert world.owner.post(path, {"phone": "11 4444-0000", "blocked": False}).status_code == 403
