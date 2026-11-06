"""Cuentas Claras's "Dar de alta un negocio": the owner's account, the invitation email from
this product's worker, and links that only work in their own product."""

from conftest import Owner, make_admin
from cuentas_claras_api.database import get_session
from cuentas_claras_api.main import app
from cuentas_claras_api.worker import job_handlers
from fastapi.testclient import TestClient
from followup_core.notifications.infrastructure.smtp import RecordingEmailSender
from followup_core.scheduling.infrastructure.queue import JobRunner
from followup_core.tenancy.domain.product import Product
from inmo24x7_api.database import get_session as inmo_get_session
from inmo24x7_api.main import app as inmo_app


def _admin(client, sessions) -> Owner:
    admin = Owner(client, "Plataforma")
    make_admin(sessions, admin.profile_id)
    return admin


def _send_emails(sessions) -> RecordingEmailSender:
    sender = RecordingEmailSender()
    runner = JobRunner(
        sessions, lambda session: job_handlers(session, sender), queue=Product.CUENTAS_CLARAS
    )
    runner.run_due()
    return sender


def test_dar_de_alta_invites_the_owner_from_cuentas_claras(client, sessions) -> None:
    admin = _admin(client, sessions)

    created = admin.post(
        "/admin/tenants",
        {"business_name": "Matafuegos Norte", "owner_email": "duenio@matafuegos.test"},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["owner_pending"] is True and len(body["temporary_password"]) == 12
    (email,) = _send_emails(sessions).sent
    assert email.to == ["duenio@matafuegos.test"]
    assert "Cuentas Claras" in email.subject and "Matafuegos Norte" in email.subject
    assert "http://localhost:5175/invitacion?token=" in email.text
    token = email.text.split("invitacion?token=", 1)[1].split()[0]
    assert client.get(f"/invitations/{token}").json()["business_name"] == "Matafuegos Norte"
    # The same link means nothing to inmo24x7's API (same database).
    inmo_app.dependency_overrides[inmo_get_session] = app.dependency_overrides[get_session]
    try:
        with TestClient(inmo_app) as inmo:
            assert inmo.get(f"/invitations/{token}").status_code == 404
            accepted = inmo.post("/invitations/accept", json={"token": token, "password": "x" * 10})
            assert accepted.status_code == 404
    finally:
        inmo_app.dependency_overrides.pop(inmo_get_session, None)
    assert client.get(f"/invitations/{token}").json()["status"] == "valid"


def test_only_admins_create_businesses(client, sessions) -> None:
    owner = Owner(client)

    response = owner.post("/admin/tenants", {"business_name": "Otra", "owner_email": "otra@x.test"})

    assert response.status_code == 403
