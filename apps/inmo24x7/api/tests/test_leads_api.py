"""Leads created from simulator conversations, and the Consultas endpoints."""

from datetime import datetime, time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from followup_core.conversation.application.threads import utc_now
from inmo24x7_api.leads.tools import HAND_OFF_EVENT
from sqlalchemy import text
from test_setup_endpoints import Account, _body, _set_role


@pytest.fixture
def owner(client: TestClient, auth) -> Account:
    account = Account(client, auth)
    # Open every day, all day, so the test never depends on the time it runs.
    setup = account.get("/agent-setup").json()
    always = [{"weekday": day, "opens": "00:00", "closes": "23:30"} for day in range(7)]
    assert account.put("/agent-setup", _body(setup, business_hours=always)).status_code == 200
    return account


def _say(account: Account, message: str, path: str = "/simulator") -> dict:
    response = account.post(f"{path}/messages", {"text": message})
    assert response.status_code == 200, response.json()
    return response.json()


def _visit_conversation(account: Account, path: str = "/simulator") -> None:
    for message in ["Hola", "Quiero alquilar", "Palermo"]:
        _say(account, message, path)
    offer = _say(account, "Me interesa la primera", path)["messages"][-1]
    assert offer["slots"] and len(offer["slots"]) == 2
    _say(account, offer["slots"][0]["label"], path)
    _say(account, "Me llamo Ana Pérez", path)
    _say(account, "11 5555-1234", path)


def test_the_first_message_creates_one_test_lead_per_thread(owner: Account, db_session) -> None:
    _say(owner, "Hola")
    _say(owner, "Quiero alquilar")

    rows = db_session.execute(text("SELECT is_test, status, answers FROM leads")).all()
    assert len(rows) == 1
    is_test, status, answers = rows[0]
    assert (is_test, status, answers) == (True, "qualifying", {"operation": "alquiler"})

    owner.post("/simulator/reset", {})
    _say(owner, "Hola")
    assert db_session.execute(text("SELECT count(*) FROM leads")).scalar() == 2


def test_done_when_lead_is_listed_with_its_status_visit_and_transcript(owner: Account) -> None:
    _visit_conversation(owner)

    assert owner.get("/leads").json()["total"] == 0  # simulator leads are hidden by default
    listing = owner.get("/leads?include_test=true").json()
    (lead,) = listing["items"]
    assert lead["visitor_name"] == "Ana Pérez"
    assert lead["contact"] == "+54 9 11 5555-1234"
    assert lead["looking_for"] == "Alquiler · Palermo"
    assert (lead["status"], lead["is_test"], lead["hand_off_reason"]) == (
        "visit_proposed",
        True,
        "visit",
    )
    assert lead["handed_off_at"] is not None

    detail = owner.get(f"/leads/{lead['id']}").json()
    assert [change["status"] for change in detail["status_history"]] == [
        "qualifying",
        "visit_proposed",
    ]
    (visit,) = detail["visits"]
    assert visit["status"] == "proposed"
    assert visit["property_id"] is None  # a sample listing: no own properties yet
    starts_at = datetime.fromisoformat(visit["starts_at"])
    assert starts_at > utc_now()
    events = [m for m in detail["transcript"] if m["author"] == "system"]
    assert [m["text"] for m in events] == [HAND_OFF_EVENT]
    answers = {row["key"]: row["value"] for row in detail["answers"]}
    assert answers["operation"] == "Alquiler"
    assert answers["contact"] == "+54 9 11 5555-1234"


def test_own_property_visits_and_matches_point_to_the_property(owner: Account, db_session) -> None:
    sample = Path(__file__).resolve().parents[4] / "docs" / "samples" / "propiedades.csv"
    owner.client.post(
        "/properties/import",
        files={"file": ("propiedades.csv", sample.read_bytes())},
        headers=owner.headers,
    )
    _visit_conversation(owner)

    (lead,) = owner.get("/leads?include_test=true").json()["items"]
    (visit,) = owner.get(f"/leads/{lead['id']}").json()["visits"]
    assert visit["property_id"] is not None
    # Cards come cheapest first: the monoambiente is "la primera".
    assert visit["property_label"] == "Monoambiente amoblado · Charcas 4100"
    matched = db_session.execute(text("SELECT count(*) FROM lead_property_matches")).scalar()
    assert matched and matched > 0


def test_asking_for_a_person_sets_human_requested(owner: Account) -> None:
    _say(owner, "Hola")
    reply = _say(owner, "Quiero hablar con una persona")

    assert reply["messages"][-1]["author"] == "system"
    page = owner.get("/leads?include_test=true&tab=attention").json()
    (lead,) = page["items"]
    assert lead["status"] == "human_requested"
    assert lead["needs_attention"] is True
    assert page["counts"] == {"attention": 1, "visits": 0, "all": 1}


def test_real_leads_are_listed_without_the_test_flag(owner: Account, db_session) -> None:
    _say(owner, "Hola")
    db_session.execute(text("UPDATE leads SET is_test = false"))
    db_session.commit()

    (lead,) = owner.get("/leads").json()["items"]
    assert lead["is_test"] is False


def test_leads_are_scoped_to_the_tenant(client: TestClient, auth, owner: Account) -> None:
    _say(owner, "Hola")
    (lead,) = owner.get("/leads?include_test=true").json()["items"]
    other = Account(client, auth, "Agencia B")

    assert other.get("/leads?include_test=true").json()["total"] == 0
    assert other.get(f"/leads/{lead['id']}").json() == {"code": "lead_not_found"}


def test_every_role_can_read_leads(owner: Account, db_session) -> None:
    _say(owner, "Hola")
    _set_role(db_session, owner.user_id, "viewer")

    assert owner.get("/leads?include_test=true").json()["total"] == 1


def test_admin_simulator_threads_are_test_leads_of_the_tenant(
    client: TestClient, auth, owner: Account
) -> None:
    admin = Account(client, auth, "Plataforma")
    auth.make_admin(admin.user_id)

    _say(admin, "Hola", f"/admin/tenants/{owner.tenant_id}/simulator")

    (lead,) = owner.get("/leads?include_test=true").json()["items"]
    assert lead["is_test"] is True
    assert admin.get("/leads?include_test=true").json()["total"] == 0


def test_team_hours_decide_the_slots(client: TestClient, auth) -> None:
    account = Account(client, auth)
    setup = account.get("/agent-setup").json()
    tuesday_only = [{"weekday": 1, "opens": "10:00", "closes": "12:00"}]
    account.put("/agent-setup", _body(setup, business_hours=tuesday_only))
    for message in ["Hola", "Quiero alquilar", "Palermo"]:
        _say(account, message)

    offer = _say(account, "la primera")["messages"][-1]

    for slot in offer["slots"]:
        weekday, hour = slot["label"].split(",")[0].split()[0], slot["label"].split(", ")[1]
        assert weekday == "martes"
        assert time(10) <= time.fromisoformat(hour) < time(12)


def test_picking_another_slot_replaces_the_proposed_visit(owner: Account) -> None:
    for message in ["Hola", "Quiero alquilar", "Palermo"]:
        _say(owner, message)
    offer = _say(owner, "Me interesa la primera")["messages"][-1]
    first, second = offer["slots"]
    owner.post("/simulator/messages", {"text": first["label"], "choice_id": first["id"]})
    owner.post("/simulator/messages", {"text": second["label"], "choice_id": second["id"]})

    (lead,) = owner.get("/leads?include_test=true").json()["items"]
    visits = owner.get(f"/leads/{lead['id']}").json()["visits"]
    assert [visit["status"] for visit in visits] == ["cancelled", "proposed"]
    assert visits[0]["starts_at"] != visits[1]["starts_at"]
    assert lead["status"] == "visit_proposed"
