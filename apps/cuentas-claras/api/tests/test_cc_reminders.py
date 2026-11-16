"""Reminders end to end on the test database: connect WhatsApp (templates created and
approved through Meta's webhook), plan, send through a fake Graph API, record the events,
and what the owner sees (C4, "Lo próximo", the payment page, the emails)."""

from datetime import date, timedelta
from uuid import UUID

import pytest
from cuentas_claras_api import container
from reminder_fakes import CLIENT_TO, CLIENT_WA_ID, World, at

TODAY = date.today()
# The next Monday (never today): every scenario starts in the future, so the jobs the API
# enqueues on the real clock are already due on the test's clock.
MONDAY = TODAY + timedelta(days=(7 - TODAY.weekday()) % 7 or 7)


def dd_mm(day: date) -> str:
    return f"{day:%d/%m}"


@pytest.fixture
def world(client, sessions, monkeypatch) -> World:
    # Holidays have their own tests; here a Monday is always a sending day.
    monkeypatch.setattr(container, "argentine_holidays", lambda years: frozenset())
    return World(client, sessions, at(MONDAY, 10))


def template_id(world: World, slug: str) -> str:
    return next(key for key, item in world.graph.templates.items() if slug in item["name"])


def parameters(message: dict) -> tuple[list[str], str]:
    body, button = message["template"]["components"]
    return [item["text"] for item in body["parameters"]], button["parameters"][0]["text"]


def invoice(world: World, invoice_id: UUID) -> dict:
    response = world.owner.get(f"/invoices/{invoice_id}")
    assert response.status_code == 200
    return response.json()


def test_connecting_whatsapp_creates_the_templates_and_metas_review_reaches_c4(world) -> None:
    assert world.connect().status_code == 200
    world.run()

    created = [body for method, path, body in world.graph.requests if path.endswith("templates")]
    assert sorted(body["name"] for body in created) == [
        "cuentas_claras_antes_v1",
        "cuentas_claras_varias_v1",
        "cuentas_claras_vence_hoy_v1",
        "cuentas_claras_vencida_v1",
    ]
    assert all(body["category"] == "UTILITY" and body["language"] == "es_AR" for body in created)
    pending = world.owner.get("/reminders").json()
    assert {item["status_label"] for item in pending["templates"]} == {"en revisión"}

    assert world.template_status(template_id(world, "antes"), "REJECTED", "INVALID_FORMAT") == 200
    assert world.template_status(template_id(world, "vencida"), "APPROVED") == 200

    templates = {item["kind"]: item for item in world.owner.get("/reminders").json()["templates"]}
    assert templates["before"]["status_label"] == "rechazada: el formato no es válido"
    assert templates["after"]["status"] == "approved"
    assert templates["due"]["status_label"] == "en revisión"
    assert world.owner.get("/onboarding").json()["checklist"]["facts"]["whatsapp_connected"] is True


def test_the_periodic_sync_reads_metas_status_when_the_webhook_never_came(world) -> None:
    world.connect()
    world.run()
    world.graph.review("APPROVED")

    response = world.admin.client.post(
        f"/admin/tenants/{world.owner.tenant_id}/reminders/templates/sync",
        headers=world.admin.headers,
    )
    world.run()

    assert response.status_code == 202
    statuses = {item["status"] for item in world.owner.get("/reminders").json()["templates"]}
    assert statuses == {"approved"}


def test_a_due_invoice_gets_one_reminder_with_its_payment_link(world, client) -> None:
    world.ready()
    client_id, [invoice_id] = world.client_with_invoices(MONDAY + timedelta(days=3))

    world.run()  # the invoice's own planning, then the send job

    [message] = world.reminder_messages()
    assert message["to"] == CLIENT_TO
    assert message["template"]["name"] == "cuentas_claras_antes_v1"
    fields, token = parameters(message)
    assert fields == [
        "Edificio Güemes",
        "Ascensores Delta",
        "B 0003-00001201",
        "$ 180.000,00",
        dd_mm(MONDAY + timedelta(days=3)),
    ]
    assert world.events() == [("sent", None)]

    page = client.get(f"/pay/{token}")
    assert page.status_code == 200
    assert page.headers["X-Robots-Tag"].startswith("noindex")
    body = page.json()
    assert (body["business_name"], body["client_name"]) == ("Ascensores Delta", "Edificio Güemes")
    assert body["totals"] == [{"currency": "ARS", "amount": "180000.00"}]
    assert body["mercado_pago_available"] is False
    assert "pagos@guemes.test" not in page.text and "cuit" not in page.text

    # Running the planner again sends nothing more: one reminder per client and day.
    assert world.plan()["sends"] == 0
    world.run()
    assert len(world.reminder_messages()) == 1
    assert world.owner.get("/reminders").json()["month_count"] == 1
    assert invoice(world, invoice_id)["next_action"] == (
        f"Recordatorio el {dd_mm(MONDAY + timedelta(days=3))} 9:00"
    )
    transcript = world.sql(
        "SELECT m.direction, m.text FROM conversation_messages m JOIN conversation_threads t "
        "ON t.id = m.thread_id WHERE t.visitor_id = :v",
        v=CLIENT_WA_ID,
    )
    assert [row.direction for row in transcript] == ["outbound"]
    assert transcript[0].text.startswith("Hola Edificio Güemes, te escribimos de Ascensores Delta")


def test_several_invoices_of_a_client_due_the_same_day_go_in_one_message(world) -> None:
    world.ready()
    due = MONDAY + timedelta(days=3)
    world.client_with_invoices(due, due)

    world.run()

    [message] = world.reminder_messages()
    assert message["template"]["name"] == "cuentas_claras_varias_v1"
    fields, _ = parameters(message)
    assert fields[2:4] == ["B 0003-00001201, B 0003-00001202", "$ 360.000,00"]


def test_a_promise_pauses_the_reminders_and_they_resume_the_day_after(world) -> None:
    world.ready()
    _, [invoice_id] = world.client_with_invoices(MONDAY)
    until = MONDAY + timedelta(days=2)
    promised = world.owner.post(
        f"/invoices/{invoice_id}/promise", {"promised_until": until.isoformat()}
    )

    world.run()

    assert promised.status_code == 200
    assert promised.json()["lifecycle"] == "promised"
    assert promised.json()["status"]["label"] == f"Con promesa · hasta {dd_mm(until)}"
    assert world.reminder_messages() == []
    assert invoice(world, invoice_id)["next_action"] == f"Pausado: promesa hasta {dd_mm(until)}"
    assert world.owner.get("/invoices?tab=promised").json()["counts"]["promised"] == 1

    world.clock.now = at(MONDAY + timedelta(days=3), 10)  # Thursday: the promise passed
    world.plan()
    world.run()

    [message] = world.reminder_messages()
    # The due-date step goes out late, so it says the invoice is overdue.
    assert message["template"]["name"] == "cuentas_claras_vencida_v1"
    assert invoice(world, invoice_id)["lifecycle"] == "open"


def test_removing_a_promise_lets_the_sequence_go_on(world) -> None:
    world.ready()
    _, [invoice_id] = world.client_with_invoices(MONDAY + timedelta(days=3))
    world.owner.post(
        f"/invoices/{invoice_id}/promise",
        {"promised_until": (MONDAY + timedelta(days=5)).isoformat()},
    )
    removed = world.client.delete(f"/invoices/{invoice_id}/promise", headers=world.owner.headers)

    world.run()

    assert removed.json()["lifecycle"] == "open"
    assert len(world.reminder_messages()) == 1


def test_a_revoked_token_pauses_the_business_and_nothing_goes_out_late(world) -> None:
    world.ready()
    world.graph.fail_next = [(401, 190)]
    client_id, [invoice_id] = world.client_with_invoices(MONDAY + timedelta(days=3))

    world.run()

    assert world.events() == [("skipped", "connection_error")]
    status = world.owner.get("/whatsapp").json()
    assert status["status"] == "error"
    assert status["error"]["title"] == "El permiso de Meta venció"
    assert status["error"]["message"].startswith("Los recordatorios por WhatsApp no salen")
    assert invoice(world, invoice_id)["next_action"] == "Pausado: WhatsApp desconectado"
    assert world.plan()["paused"] == "error"
    # The message is closed, not waiting: reconnecting never sends it outside its day.
    assert [row.status for row in world.sql("SELECT status FROM whatsapp_outbound")] == ["failed"]

    assert world.connect(access_token="EAAG-new-token").status_code == 200
    world.run()
    assert len(world.reminder_messages()) == 1  # only the failed attempt

    world.clock.now = at(MONDAY + timedelta(days=1), 10)
    world.plan()
    world.run()
    assert len(world.reminder_messages()) == 2
    assert world.events()[-1] == ("sent", None)


def test_a_permanent_meta_error_fails_that_reminder_and_the_next_step_still_comes(world) -> None:
    world.ready()
    world.graph.fail_next = [(400, 131026)]  # the number has no WhatsApp
    _, [invoice_id] = world.client_with_invoices(MONDAY + timedelta(days=3))

    world.run()

    assert world.events() == [("failed", "131026")]
    assert invoice(world, invoice_id)["next_action"] == (
        f"Recordatorio el {dd_mm(MONDAY + timedelta(days=3))} 9:00"
    )


def test_a_reply_is_stored_on_the_clients_thread_and_emailed_to_the_owner(world) -> None:
    world.ready()
    client_id, _ = world.client_with_invoices(MONDAY + timedelta(days=3))
    world.run()

    assert world.reply("Ya la pagué ayer, te mando el comprobante") == 200
    world.clock.advance(seconds=5)
    world.run()

    rows = world.sql(
        "SELECT m.direction, m.text FROM conversation_messages m JOIN conversation_threads t "
        "ON t.id = m.thread_id WHERE t.visitor_id = :v ORDER BY m.seq",
        v=CLIENT_WA_ID,
    )
    assert [row.direction for row in rows] == ["outbound", "inbound"]
    [email] = [item for item in world.emails.sent if item.subject.startswith("Respondió")]
    assert email.subject == (
        "Respondió: “Ya la pagué ayer, te mando el comprobante” (Edificio Güemes)"
    )
    assert f"/clientes/{client_id}" in email.text
    assert world.owner.email in email.to
    assert any(body.get("status") == "read" for _, _, body in world.graph.requests)


def test_a_template_in_review_or_rejected_does_not_send(world) -> None:
    world.connect()
    world.run()
    world.template_status(template_id(world, "antes"), "REJECTED", "INVALID_FORMAT")
    _, [invoice_id] = world.client_with_invoices(MONDAY + timedelta(days=3))

    world.run()

    assert world.reminder_messages() == []
    assert world.events() == [("skipped", "template_not_approved:before")]
    assert invoice(world, invoice_id)["next_action"] == "En espera: plantilla en revisión"


def test_editing_a_template_submits_a_new_version_and_the_approved_one_keeps_going(world) -> None:
    world.ready()
    text = "Hola {cliente}, te recordamos la factura {factura} de {negocio}. ¡Gracias!"

    edited = world.client.put(
        "/reminders/templates/before", json={"body": text}, headers=world.owner.headers
    )
    world.run()
    world.client_with_invoices(MONDAY + timedelta(days=3))
    world.run()

    assert edited.status_code == 200
    before = {item["kind"]: item for item in world.owner.get("/reminders").json()["templates"]}[
        "before"
    ]
    assert (before["version"], before["in_use_version"], before["newer_in_review"]) == (2, 1, True)
    assert before["status_label"] == "en revisión"
    assert "cuentas_claras_antes_v2" in [item["name"] for item in world.graph.templates.values()]
    [message] = world.reminder_messages()
    assert message["template"]["name"] == "cuentas_claras_antes_v1"
    bad = world.client.put(
        "/reminders/templates/before", json={"body": "{cliente} hola"}, headers=world.owner.headers
    )
    assert (bad.status_code, bad.json()["field"]) == (422, "field_at_edge")


def test_a_client_that_asked_not_to_be_written_gets_nothing(world) -> None:
    world.ready()
    client_id, [invoice_id] = world.client_with_invoices(MONDAY + timedelta(days=3))
    response = world.client.patch(
        f"/clients/{client_id}",
        json={"name": "Edificio Güemes", "whatsapp": "+54 9 11 5555-0301", "no_reminders": True},
        headers=world.owner.headers,
    )

    world.run()

    assert response.json()["no_reminders"] is True
    assert world.reminder_messages() == []
    assert invoice(world, invoice_id)["next_action"] == "Sin recordatorios (pedido del cliente)"


def test_the_send_job_checks_again_an_invoice_paid_after_planning_is_skipped(world) -> None:
    world.ready()
    world.clock.now = at(MONDAY, 8)  # before the window: the send waits until 9:00
    _, [invoice_id] = world.client_with_invoices(MONDAY + timedelta(days=3))
    world.run()
    paid = world.owner.post(
        f"/invoices/{invoice_id}/mark-paid", {"paid_at": MONDAY.isoformat(), "paid_via": "transfer"}
    )

    world.clock.now = at(MONDAY, 9, 1)
    world.run()

    assert paid.status_code == 200 and paid.json()["next_action"] is None
    assert world.reminder_messages() == []
    assert world.events() == [("skipped", "invoice_closed")]


def test_after_the_last_reminder_the_owner_is_told_and_reminders_stop(world) -> None:
    world.ready()
    _, [invoice_id] = world.client_with_invoices(MONDAY - timedelta(days=20))

    world.run()  # never reminded: the last reminder goes out first
    world.clock.now = at(MONDAY + timedelta(days=1), 10)
    world.plan()
    world.run()
    world.clock.now = at(MONDAY + timedelta(days=2), 10)
    world.plan()
    world.run()

    assert [m["template"]["name"] for m in world.reminder_messages()] == [
        "cuentas_claras_vencida_v1"
    ]
    assert [outcome for outcome, _ in world.events()] == ["sent", "escalated"]
    [email] = [item for item in world.emails.sent if item.subject.startswith("Escalar")]
    assert email.subject == "Escalar al dueño: 1 factura sin pagar"
    assert "B 0003-00001201" in email.text and "/facturas?tab=overdue" in email.text
    assert invoice(world, invoice_id)["next_action"] == "Escalado al dueño"


def test_weekends_wait_for_monday(world) -> None:
    world.ready()
    saturday = MONDAY + timedelta(days=5)
    world.clock.now = at(saturday, 10)
    _, [invoice_id] = world.client_with_invoices(saturday + timedelta(days=3))

    world.run()

    assert world.reminder_messages() == []
    monday = saturday + timedelta(days=2)
    assert invoice(world, invoice_id)["next_action"] == f"Recordatorio el {dd_mm(monday)} 9:00"


def test_the_policy_is_editable_and_validated(world) -> None:
    settings = world.owner.get("/reminders").json()
    assert settings["configured"] is False
    assert [step["label"] for step in settings["steps"]] == [
        "3 días antes",
        "El día del vencimiento",
        "7 días después",
        "15 días después: avisar al dueño",
    ]
    steps = [
        {"id": step["id"], "offset_days": step["offset_days"], "kind": step["kind"]}
        for step in settings["steps"]
    ]

    duplicate = world.client.put(
        "/reminders",
        json={"steps": [*steps, {"offset_days": 7}], "window": {"preset": "mornings"}},
        headers=world.owner.headers,
    )
    escalation_first = world.client.put(
        "/reminders",
        json={"steps": [*steps, {"offset_days": 30}], "window": {"preset": "mornings"}},
        headers=world.owner.headers,
    )
    saved = world.client.put(
        "/reminders",
        json={
            "steps": [*steps[:3], {"offset_days": 10}, steps[3]],
            "window": {"preset": "custom", "start": "14:00", "end": "17:30"},
            "skip_holidays": False,
            "pause_on_promise": True,
        },
        headers=world.owner.headers,
    )

    assert (duplicate.status_code, duplicate.json()["field"]) == (422, "offset_duplicate")
    assert (escalation_first.status_code, escalation_first.json()["field"]) == (
        422,
        "escalation_last",
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["configured"] is True
    assert [step["offset_days"] for step in body["steps"]] == [-3, 0, 7, 10, 15]
    assert body["steps"][0]["id"] == steps[0]["id"]
    assert body["window"] == {"preset": "custom", "start": "14:00", "end": "17:30"}
    assert (
        world.owner.get("/onboarding").json()["checklist"]["facts"]["reminders_configured"] is True
    )


def test_the_payment_page_is_the_same_404_for_unknown_and_malformed_links(world, client) -> None:
    unknown = client.get("/pay/" + "A" * 43)
    malformed = client.get("/pay/x")

    assert unknown.status_code == malformed.status_code == 404
    assert unknown.json() == malformed.json() == {"code": "payment_link_not_found"}


def test_transfer_details_show_on_the_payment_page(world, client) -> None:
    world.ready()
    saved = world.client.put(
        "/payment-settings",
        json={"cbu_or_alias": "ascensores.delta", "holder": "Ascensores Delta SRL", "bank": ""},
        headers=world.owner.headers,
    )
    world.client_with_invoices(MONDAY + timedelta(days=3))
    world.run()
    _, token = parameters(world.reminder_messages()[0])

    page = client.get(f"/pay/{token}").json()

    assert saved.json()["transfer"]["cbu_or_alias"] == "ascensores.delta"
    assert page["transfer"] == {
        "cbu_or_alias": "ascensores.delta",
        "holder": "Ascensores Delta SRL",
        "bank": None,
    }
    invalid = world.client.put(
        "/payment-settings", json={"cbu_or_alias": "12", "holder": "x"}, headers=world.owner.headers
    )
    assert (invalid.status_code, invalid.json()["field"]) == (422, "cbu_or_alias")


def test_the_webhook_takes_only_cuentas_claras_own_meta_app(world) -> None:
    assert world.reply("hola", sender=CLIENT_WA_ID) == 200
    assert world.post({"object": "whatsapp_business_account"}, secret="dev-app-secret") == 401


def test_the_backoffice_shows_template_statuses_and_the_last_errors(world) -> None:
    world.connect()
    world.run()
    world.template_status(template_id(world, "antes"), "PAUSED")
    world.client_with_invoices(MONDAY + timedelta(days=3))
    world.run()

    response = world.admin.client.get(
        f"/admin/tenants/{world.owner.tenant_id}/reminders", headers=world.admin.headers
    )

    assert response.status_code == 200
    body = response.json()
    assert {(t["kind"], t["status_label"]) for t in body["templates"]} >= {
        ("before", "pausada por Meta"),
        ("due", "en revisión"),
    }
    [error] = body["errors"]
    assert (error["outcome"], error["reason_label"]) == (
        "skipped",
        "La plantilla no está aprobada",
    )
    owner_try = world.owner.get(f"/admin/tenants/{world.owner.tenant_id}/reminders")
    assert owner_try.status_code == 403
