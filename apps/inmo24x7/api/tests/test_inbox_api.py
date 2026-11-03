"""The inbox list (tabs, counts, ordering, search, scoping), the needs-attention rule in the
domain and in SQL, and the CSV export."""

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from inbox_fakes import add_lead
from inmo24x7_api.leads.application import queries
from inmo24x7_api.leads.domain.lead import Lead, LeadStatus, VisitStatus
from inmo24x7_api.leads.domain.repositories import Search
from test_setup_endpoints import Account

NOW = datetime.now(UTC)
HOUR = timedelta(hours=1)


@pytest.fixture
def owner(client: TestClient, auth) -> Account:
    return Account(client, auth)


@pytest.fixture
def inbox(owner: Account, db_session) -> dict[str, Lead]:
    tenant = owner.tenant_id
    leads = {
        # Asked for a person: always first in "Para atender".
        "human": add_lead(
            db_session,
            tenant,
            created_at=NOW - 5 * HOUR,
            name="Bruno Díaz",
            contact="+54 9 11 4444-0000",
            answers={"operation": "alquiler", "zone": "Belgrano"},
            status=LeadStatus.HUMAN_REQUESTED,
            handed_off_at=NOW - 4 * HOUR,
        ),
        # Two proposed visits: the soonest visit first.
        "later_visit": add_lead(
            db_session,
            tenant,
            created_at=NOW - 3 * HOUR,
            name="Carla Gómez",
            contact="+54 9 11 5555-0188",
            answers={"operation": "alquiler", "zone": "Palermo"},
            status=LeadStatus.VISIT_PROPOSED,
            handed_off_at=NOW - 3 * HOUR,
            visits=[(NOW + 48 * HOUR, VisitStatus.PROPOSED)],
        ),
        "sooner_visit": add_lead(
            db_session,
            tenant,
            created_at=NOW - 2 * HOUR,
            name="Ana Pérez",
            contact="+54 9 351 456-7890",
            answers={"operation": "venta", "zone": "Ñuñoa"},
            status=LeadStatus.VISIT_PROPOSED,
            handed_off_at=NOW - 2 * HOUR,
            visits=[(NOW + 24 * HOUR, VisitStatus.PROPOSED)],
        ),
        # The team already answered after the hand-off: not waiting any more.
        "answered": add_lead(
            db_session,
            tenant,
            created_at=NOW - 6 * HOUR,
            name="Diego",
            status=LeadStatus.HUMAN_REQUESTED,
            handed_off_at=NOW - 6 * HOUR,
            last_human_reply_at=NOW - 5 * HOUR,
        ),
        "confirmed": add_lead(
            db_session,
            tenant,
            created_at=NOW - 8 * HOUR,
            name="Elena",
            status=LeadStatus.VISIT_CONFIRMED,
            handed_off_at=NOW - 8 * HOUR,
            visits=[(NOW + 72 * HOUR, VisitStatus.CONFIRMED)],
        ),
        "qualifying": add_lead(
            db_session,
            tenant,
            created_at=NOW - HOUR,
            name="Fede",
            last_activity_at=NOW - 10 * 60 * timedelta(seconds=1),
        ),
        "test": add_lead(
            db_session,
            tenant,
            created_at=NOW - HOUR,
            name="Prueba Simulador",
            status=LeadStatus.HUMAN_REQUESTED,
            handed_off_at=NOW - HOUR,
            is_test=True,
        ),
    }
    return leads


def _names(owner: Account, query: str) -> list[str]:
    return [item["visitor_name"] for item in owner.get(f"/leads?{query}").json()["items"]]


def test_tabs_have_counts_and_their_own_order(owner: Account, inbox) -> None:
    page = owner.get("/leads?tab=attention").json()

    assert page["counts"] == {"attention": 3, "visits": 3, "all": 6}
    assert page["page_size"] == 25
    assert [item["visitor_name"] for item in page["items"]] == [
        "Bruno Díaz",
        "Ana Pérez",
        "Carla Gómez",
    ]
    assert all(item["needs_attention"] for item in page["items"])
    assert _names(owner, "tab=visits") == ["Ana Pérez", "Carla Gómez", "Elena"]
    assert _names(owner, "tab=all")[0] == "Fede"
    visits = owner.get("/leads?tab=visits").json()["items"]
    assert visits[0]["next_visit_at"] is not None


def test_test_leads_count_only_with_the_toggle(owner: Account, inbox) -> None:
    counts = owner.get("/leads?tab=attention&include_test=true").json()["counts"]

    assert counts == {"attention": 4, "visits": 3, "all": 7}


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("q=ana", ["Ana Pérez"]),
        ("q=PEREZ", ["Ana Pérez"]),
        ("q=nunoa", ["Ana Pérez"]),  # accent-insensitive (Ñuñoa)
        ("q=palermo", ["Carla Gómez"]),
        ("q=11%205555-0188", ["Carla Gómez"]),
        ("q=%2B5491155550188", ["Carla Gómez"]),
        ("q=011%2015%205555%200188", ["Carla Gómez"]),
        ("q=5555", ["Carla Gómez"]),
        ("q=0351%20456-7890", ["Ana Pérez"]),
        ("q=nadie", []),
        ("q=%25", []),  # a LIKE wildcard is a literal
    ],
)
def test_search_by_name_zone_and_phone_in_any_format(
    owner: Account, inbox, query: str, expected: list[str]
) -> None:
    assert _names(owner, f"tab=all&{query}") == expected


def test_search_narrows_the_counts_too(owner: Account, inbox) -> None:
    counts = owner.get("/leads?q=alquiler").json()["counts"]

    assert counts == {"attention": 2, "visits": 1, "all": 2}


def test_another_tenant_sees_nothing(client, auth, inbox) -> None:
    stranger = Account(client, auth, "Otra inmobiliaria")

    page = stranger.get("/leads?tab=all&include_test=true").json()

    assert page["items"] == []
    assert page["counts"] == {"attention": 0, "visits": 0, "all": 0}


def test_the_domain_rule_and_the_sql_agree(owner: Account, inbox) -> None:
    listed = {
        item["id"] for item in owner.get("/leads?tab=attention&include_test=true").json()["items"]
    }

    expected = {str(lead.id) for lead in inbox.values() if lead.needs_attention}
    assert listed == expected


def test_search_parsing() -> None:
    assert Search.parse("  ") == Search()
    assert Search.parse("Ñuñoa") == Search(text="nunoa")
    assert Search.parse("11 5555-0188") == Search(digits="5491155550188")
    assert Search.parse("5555") == Search(digits="5555")
    assert Search.parse("2 amb") == Search(text="2 amb")


# --- CSV export -------------------------------------------------------------------------------


def _csv(owner: Account, query: str = "") -> tuple[bytes, list[list[str]]]:
    response = owner.get(f"/leads/export.csv?{query}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].startswith('attachment; filename="consultas-')
    raw = response.content
    return raw, list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))


def test_the_export_opens_in_excel_with_the_configured_questions(owner: Account, inbox) -> None:
    raw, rows = _csv(owner)

    assert raw.startswith(b"\xef\xbb\xbf")
    header = rows[0]
    labels = [
        q["label"]
        for q in owner.get("/agent-setup").json()["config"]["qualification_questions"]
        if q["enabled"]
    ]
    assert header[:5] == ["Fecha de alta", "Nombre", "Teléfono", "Canal", "Estado"]
    assert header[5 : 5 + len(labels)] == labels
    assert header[-3:] == ["Visita (fecha y propiedad)", "Estado de la visita", "Última actividad"]
    assert len(rows) == 1 + 6  # test leads excluded
    carla = next(row for row in rows if row[1] == "Carla Gómez")
    assert (carla[2], carla[3], carla[4]) == ("+54 9 11 5555-0188", "WhatsApp", "Visita propuesta")
    assert carla[-3].endswith("· Depto · Gorriti 4800") and carla[-2] == "Propuesta"


def test_the_export_follows_the_tab_search_and_toggle(owner: Account, inbox) -> None:
    _, attention = _csv(owner, "tab=attention")
    _, everything = _csv(owner, "include_test=true")
    _, searched = _csv(owner, "q=belgrano")

    assert [row[1] for row in attention[1:]] == ["Bruno Díaz", "Ana Pérez", "Carla Gómez"]
    assert len(everything) == 1 + 7
    assert [row[1] for row in searched[1:]] == ["Bruno Díaz"]


def test_the_export_has_a_row_limit(owner: Account, inbox, monkeypatch) -> None:
    monkeypatch.setattr(queries, "EXPORT_LIMIT", 2)

    _, rows = _csv(owner)

    assert len(rows) == 1 + 2
