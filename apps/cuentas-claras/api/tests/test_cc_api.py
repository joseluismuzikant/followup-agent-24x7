"""The Cuentas Claras API: Facturas tabs and search, actions, Clientes, Inicio's summary,
roles, error codes, and the backoffice."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from conftest import Owner, make_admin
from cuentas_claras_api.container import get_clock
from cuentas_claras_api.main import app
from sqlalchemy import text

NOW = datetime(2026, 11, 2, 15, tzinfo=UTC)


@pytest.fixture(autouse=True)
def pinned_clock(client):
    app.dependency_overrides[get_clock] = lambda: lambda: NOW


@pytest.fixture
def delta(owner: Owner) -> Owner:
    assert owner.import_sample().json()["created"] == 40
    return owner


def test_tabs_have_counts_and_rows_like_c2(delta: Owner) -> None:
    body = delta.get("/invoices").json()

    # Every sample payment is from October: none counts as paid this month on 2 November.
    assert body["counts"] == {"pending": 32, "overdue": 13, "promised": 0, "paid_this_month": 0}
    assert (body["total"], body["page_size"], body["total_pages"]) == (32, 25, 2)
    first = body["items"][0]
    assert first["client_name"] == "Sanatorio Flores"
    assert first["client_subtitle"] == "Montacargas"
    assert first["number"] == "B 0003-00001225"
    assert first["status"] == {"kind": "overdue", "label": "Vencida · 60 días", "days_overdue": 60}
    # No WhatsApp connected yet: nothing can go out ("Lo próximo" says so).
    assert first["next_action"] == "Falta conectar WhatsApp"
    assert len(delta.get("/invoices?page=2").json()["items"]) == 7

    overdue = delta.get("/invoices?tab=overdue").json()["items"]
    assert len(overdue) == 13 and all(item["status"]["kind"] == "overdue" for item in overdue)
    assert delta.get("/invoices?tab=promised").json()["items"] == []
    due_soon = [i for i in body["items"] if i["status"]["kind"] == "due_soon"]
    assert due_soon and all(i["status"]["label"] == "Por vencer" for i in due_soon)


@pytest.mark.parametrize("q", ["1245", "0003-00001245", "B 3-1245", "b0003 00001245"])
def test_search_by_invoice_number_in_any_format(delta: Owner, sessions, q: str) -> None:
    with sessions() as session:
        session.execute(text("UPDATE cc_invoices SET number = 1245 WHERE number = 1203"))
        session.commit()

    items = delta.get("/invoices", params={"q": q}).json()["items"]

    assert [item["number"] for item in items] == ["B 0003-00001245"]


def test_search_by_client_name_or_cuit(delta: Owner) -> None:
    by_name = delta.get("/invoices", params={"q": "guemes"}).json()
    assert {item["client_name"] for item in by_name["items"]} == {"Consorcio Güemes 2140"}
    assert by_name["counts"]["pending"] == 2

    cuit = delta.get("/clients", params={"q": "Güemes"}).json()["items"][0]["cuit"]
    by_cuit = delta.get("/invoices", params={"q": cuit.replace("-", "")[2:10]}).json()
    assert {item["client_name"] for item in by_cuit["items"]} == {"Consorcio Güemes 2140"}


def test_summary_for_inicio(delta: Owner) -> None:
    body = delta.get("/summary").json()

    assert body["to_collect"]["count"] == 32
    assert body["overdue"]["count"] == 13
    assert body["to_collect_usd"] == {"amount": "0.00", "count": 0}
    assert float(body["to_collect"]["amount"]) > float(body["overdue"]["amount"]) > 0


def test_mark_paid_and_cancel_from_the_drawer(delta: Owner, sessions) -> None:
    first = delta.get("/invoices?tab=overdue").json()["items"][0]

    paid = delta.post(
        f"/invoices/{first['id']}/mark-paid",
        {"paid_at": "2026-11-02", "paid_via": "transfer", "reference": "op-77"},
    ).json()
    assert paid["status"]["label"] == "Pagada · Transferencia"
    assert paid["payment"] == {
        "paid_at": "2026-11-02",
        "paid_via": "transfer",
        "paid_via_label": "Transferencia",
        "reference": "op-77",
    }
    again = delta.post(
        f"/invoices/{first['id']}/mark-paid", {"paid_at": "2026-11-02", "paid_via": "manual"}
    )
    assert (again.status_code, again.json()["code"]) == (409, "invoice_already_paid")

    second = delta.get("/invoices?tab=overdue").json()["items"][0]
    cancelled = delta.post(f"/invoices/{second['id']}/cancel", {"reason": "Duplicada"}).json()
    assert (cancelled["lifecycle"], cancelled["status"]["label"]) == ("cancelled", "Anulada")
    counts = delta.get("/invoices").json()["counts"]
    assert (counts["pending"], counts["paid_this_month"]) == (30, 1)
    paid_now = delta.get("/invoices?tab=paid_this_month").json()["items"]
    assert [item["status"]["label"] for item in paid_now] == ["Pagada · Transferencia"]
    with sessions() as session:
        actions = session.scalars(
            text("SELECT action FROM audit_events WHERE action LIKE 'invoice%' ORDER BY at")
        ).all()
    assert actions[-2:] == ["invoice_paid", "invoice_cancelled"]


def test_create_and_edit_invoices_and_clients(owner: Owner) -> None:
    client = owner.post(
        "/clients",
        {"name": "Consorcio Nuevo", "cuit": "30712345671", "whatsapp": "11 5555-0100"},
    )
    assert client.status_code == 201
    created = client.json()
    assert (created["cuit"], created["whatsapp_display"]) == ("30-71234567-1", "+54 9 11 5555-0100")

    invoice = owner.post(
        "/invoices",
        {
            "client_id": created["id"],
            "invoice_type": "B",
            "point_of_sale": 3,
            "number": 1245,
            "issue_date": "2026-10-01",
            "due_date": "2026-11-05",
            "amount": "180000.50",
        },
    )
    assert invoice.status_code == 201
    body = invoice.json()
    assert (body["number"], body["amount"], body["status"]["label"]) == (
        "B 0003-00001245",
        "180000.50",
        "Por vencer",
    )
    duplicate = owner.post(
        "/invoices",
        {
            **body | {"client_id": created["id"]},
            "invoice_type": "B",
            "number": 1245,
            "point_of_sale": 3,
            "issue_date": "2026-10-01",
            "due_date": "2026-11-05",
            "amount": "1",
        },
    )
    assert duplicate.json()["code"] == "invoice_number_taken"

    edited = owner.patch(
        f"/invoices/{body['id']}",
        {
            "client_id": created["id"],
            "invoice_type": "B",
            "point_of_sale": 3,
            "number": 1246,
            "issue_date": "2026-10-01",
            "due_date": "2026-11-20",
            "amount": "200000",
        },
    ).json()
    assert (edited["number"], edited["status"]["label"]) == ("B 0003-00001246", "Pendiente")

    detail = owner.get(f"/clients/{created['id']}").json()
    assert (detail["open_invoices"], detail["owed_ars"]) == (1, "200000.00")
    assert [invoice["number"] for invoice in detail["invoices"]] == ["B 0003-00001246"]


def test_error_codes(owner: Owner) -> None:
    assert (
        owner.post("/clients", {"name": "X", "cuit": "30-71234567-8"}).json()["code"]
        == "cuit_invalid"
    )
    owner.post("/clients", {"name": "Uno", "cuit": "30712345671"})
    assert (
        owner.post("/clients", {"name": "Dos", "cuit": "30-71234567-1"}).json()["code"]
        == "cuit_taken"
    )
    invalid = owner.post("/clients", {"name": "X", "whatsapp": "123"}).json()
    assert invalid == {"code": "client_invalid", "field": "whatsapp"}
    assert owner.get(f"/clients/{uuid4()}").json()["code"] == "client_not_found"
    assert owner.get(f"/invoices/{uuid4()}").json()["code"] == "invoice_not_found"
    missing_client = owner.post(
        "/invoices",
        {
            "client_id": str(uuid4()),
            "invoice_type": "B",
            "point_of_sale": 1,
            "number": 1,
            "issue_date": "2026-10-01",
            "due_date": "2026-10-01",
            "amount": "10",
        },
    )
    assert missing_client.json()["code"] == "client_not_found"
    client_id = owner.get("/clients").json()["items"][0]["id"]
    bad_amount = owner.post(
        "/invoices",
        {
            "client_id": client_id,
            "invoice_type": "B",
            "point_of_sale": 1,
            "number": 1,
            "issue_date": "2026-10-01",
            "due_date": "2026-10-01",
            "amount": "diez",
        },
    )
    assert bad_amount.json() == {"code": "invoice_invalid", "field": "amount"}


def test_clients_list_filter_and_pagination(delta: Owner) -> None:
    body = delta.get("/clients").json()
    assert (body["total"], len(body["items"])) == (25, 25)
    missing = delta.get("/clients", params={"missing_whatsapp": True}).json()["items"]
    assert len(missing) == 4 and all(item["missing_whatsapp"] for item in missing)
    guemes = delta.get("/clients", params={"q": "güemes"}).json()["items"][0]
    assert (guemes["open_invoices"], guemes["owed_ars"]) == (2, "360000.00")


def test_viewers_read_but_never_write(delta: Owner, sessions) -> None:
    with sessions() as session:
        session.execute(
            text("UPDATE profiles SET role = 'viewer' WHERE id = :id"), {"id": delta.profile_id}
        )
        session.commit()

    assert delta.get("/invoices").status_code == 200
    assert delta.post("/clients", {"name": "X"}).status_code == 403
    assert delta.import_sample().status_code == 403


def test_another_business_never_sees_these_invoices(delta: Owner) -> None:
    other = Owner(delta.client, "Matafuegos Sur")
    invoice_id = delta.get("/invoices").json()["items"][0]["id"]

    assert other.get("/invoices").json()["counts"]["pending"] == 0
    assert other.get(f"/invoices/{invoice_id}").status_code == 404
    assert other.post(f"/invoices/{invoice_id}/cancel", {"reason": "x"}).status_code == 404


def test_the_backoffice_lists_only_cuentas_claras_businesses(delta: Owner, sessions) -> None:
    admin = Owner(delta.client, "Plataforma")
    make_admin(sessions, admin.profile_id)
    with sessions() as session:
        session.execute(
            text(
                "INSERT INTO tenants (id, product, name, slug, created_at, status, trial_ends_at)"
                " VALUES (:id, 'inmo24x7', 'Inmobiliaria Sur', 'inmobiliaria-sur', now(),"
                " 'active', now() + interval '14 days')"
            ),
            {"id": uuid4()},
        )
        session.commit()

    assert delta.get("/admin/tenants").status_code == 403
    body = admin.get("/admin/tenants").json()
    assert [row["name"] for row in body["items"]] == ["Ascensores Delta"]
    row = body["items"][0]
    assert (row["clients"], row["onboarding_done"], row["onboarding_total"]) == (25, 2, 5)
    assert admin.get("/admin/tenants", params={"q": "nada"}).json()["items"] == []

    detail = admin.get(f"/admin/tenants/{delta.tenant_id}").json()
    assert [item["key"] for item in detail["checklist"] if item["done"]] == ["account", "invoices"]
    assert "invoices_imported" in [event["action"] for event in detail["activity"]]
    suspended = admin.post(f"/admin/tenants/{delta.tenant_id}/suspend", {"reason": "Falta de pago"})
    assert suspended.json()["status"] == "suspended"
    assert delta.get("/invoices").json()["code"] == "tenant_suspended"
    admin.post(f"/admin/tenants/{delta.tenant_id}/reactivate")
    assert delta.get("/invoices").status_code == 200
