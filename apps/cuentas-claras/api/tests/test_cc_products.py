"""Two products on one platform: one person can own a business in each, and nothing of one
product (tenants, profiles, jobs) is visible from the other."""

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from conftest import Owner
from cuentas_claras_api.main import app
from followup_core.identity.domain.token_verifier import VerifiedToken
from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository
from followup_core.scheduling.domain.jobs import JobHandlers, NewJob
from followup_core.scheduling.infrastructure.queue import JobRunner, SqlAlchemyJobQueue
from followup_core.tenancy.domain.product import Product
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository
from inmo24x7_api.container import create_business_use_case as inmo_create_business
from inmo24x7_api.container import sign_up_use_case as inmo_sign_up
from sqlalchemy import text

SOURCE = Path(__file__).resolve().parents[1] / "src/cuentas_claras_api"


def _inmo_business(sessions, user_id, email):
    with sessions() as session:
        inmo_create_business(session).execute(uuid4(), "Inmobiliaria Sur", "inmobiliaria", email)
        result = inmo_sign_up(session).execute(user_id, email)
        session.commit()
    return result


def test_one_email_owns_a_business_in_each_product(client, sessions) -> None:
    user_id = uuid4()
    inmo = _inmo_business(sessions, user_id, f"{user_id}@example.com")

    cuentas = Owner(client, "Ascensores Delta", user_id=user_id)

    # The first profile kept the user id (as before two products); the second has its own.
    assert inmo.profile.id == user_id
    assert cuentas.profile_id != user_id
    assert cuentas.tenant_id != inmo.tenant.id
    with sessions() as session:
        rows = session.execute(
            text("SELECT product, user_id FROM profiles WHERE user_id = :u ORDER BY product"),
            {"u": user_id},
        ).all()
    assert [(row.product, row.user_id) for row in rows] == [
        ("cuentas_claras", user_id),
        ("inmo24x7", user_id),
    ]
    assert cuentas.get("/me").json()["tenant"]["name"] == "Ascensores Delta"


def test_an_inmo24x7_account_has_no_cuentas_claras_business(client, sessions) -> None:
    user_id = uuid4()
    inmo = _inmo_business(sessions, user_id, "dueno@inmobiliariasur.test")
    token = f"tok-{user_id}"
    app.state.test_verifier.register(token, VerifiedToken(user_id, "dueno@inmobiliariasur.test"))
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/me", headers=headers)
    assert (me.status_code, me.json()["code"]) == (404, "profile_not_found")
    assert client.get("/invoices", headers=headers).status_code == 404

    # Nor can a Cuentas Claras admin open the inmo24x7 business from its backoffice.
    admin = Owner(client, "Plataforma")
    with sessions() as session:
        session.execute(
            text("UPDATE profiles SET is_platform_admin = true WHERE id = :id"),
            {"id": admin.profile_id},
        )
        session.commit()
    assert admin.get(f"/admin/tenants/{inmo.tenant.id}").status_code == 404


def test_tenant_lists_and_lookups_never_cross_products(client, sessions) -> None:
    cuentas = Owner(client, "Inmobiliaria Sur")  # the same name (and slug) is fine per product
    inmo = _inmo_business(sessions, uuid4(), "otro@example.com")

    with sessions() as session:
        inmo_tenants = SqlAlchemyTenantRepository(session, Product.INMO24X7)
        cc_tenants = SqlAlchemyTenantRepository(session, Product.CUENTAS_CLARAS)
        assert inmo_tenants.get_by_id(cuentas.tenant_id) is None
        assert cc_tenants.get_by_id(inmo.tenant.id) is None
        assert [t.id for t in cc_tenants.list_page(1, 50)] == [cuentas.tenant_id]
        assert (inmo_tenants.count(), cc_tenants.count()) == (1, 1)
        slugs = session.execute(text("SELECT product, slug FROM tenants ORDER BY product")).all()
        cc_profiles = SqlAlchemyProfileRepository(session, Product.CUENTAS_CLARAS)
        assert cc_profiles.get_by_email("otro@example.com") is None
    assert [tuple(row) for row in slugs] == [
        ("cuentas_claras", "inmobiliaria-sur"),
        ("inmo24x7", "inmobiliaria-sur"),
    ]


def test_each_worker_claims_only_its_own_queue(sessions) -> None:
    now = datetime.now(UTC)
    with sessions() as session:
        inmo_queue = SqlAlchemyJobQueue(session, lambda: now, Product.INMO24X7)
        cc_queue = SqlAlchemyJobQueue(session, lambda: now, Product.CUENTAS_CLARAS)
        # The same dedupe key is a different job in each queue.
        assert inmo_queue.enqueue(NewJob("x.inmo", {}, dedupe_key="daily:2026-11-02"))
        assert cc_queue.enqueue(NewJob("x.cc", {}, dedupe_key="daily:2026-11-02"))
        assert not cc_queue.enqueue(NewJob("x.cc", {}, dedupe_key="daily:2026-11-02"))
        session.commit()

    ran: list[str] = []
    handlers = JobHandlers(
        [("x.inmo", lambda job: ran.append(job.kind)), ("x.cc", lambda job: ran.append(job.kind))]
    )
    later = lambda: now + timedelta(seconds=1)  # noqa: E731
    cc_runner = JobRunner(sessions, lambda _s: handlers, later, queue=Product.CUENTAS_CLARAS)

    assert cc_runner.run_due() == 1
    assert ran == ["x.cc"]
    with sessions() as session:
        statuses = dict(session.execute(text("SELECT kind, status FROM jobs")).all())
    assert statuses == {"x.inmo": "queued", "x.cc": "done"}


def test_cuentas_claras_always_names_its_product() -> None:
    """Core's adapters default to the first product (inmo24x7) for code written before
    there were two; every Cuentas Claras call passes its own key."""
    scoped = {
        "SqlAlchemyTenantRepository",
        "SqlAlchemyProfileRepository",
        "SqlAlchemyOwnerClaimRepository",
        "SqlAlchemyJobQueue",
        "JobRunner",
        "build_auth",
    }
    unscoped = []
    for path in SOURCE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in scoped:
                names = {
                    n.id
                    for arg in [*node.args, *(k.value for k in node.keywords)]
                    for n in ast.walk(arg)
                    if isinstance(n, ast.Name)
                }
                if "PRODUCT" not in names:
                    unscoped.append(f"{path.name}:{node.lineno}")
    assert unscoped == []
