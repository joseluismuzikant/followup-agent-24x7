"""scripts/seed_dev.py's reminders setup: Ascensores Delta can send reminders locally (a log
sender number, approved templates, a saved policy), and running it again changes nothing."""

import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))

import seed_dev  # noqa: E402

COUNTS = (
    "SELECT (SELECT count(*) FROM whatsapp_connections c JOIN tenants t ON t.id = c.tenant_id "
    "        WHERE t.product = 'cuentas_claras'),"
    "       (SELECT count(*) FROM cc_whatsapp_templates WHERE status = 'APPROVED'),"
    "       (SELECT count(*) FROM cc_reminder_policies WHERE configured_at IS NOT NULL),"
    "       (SELECT count(*) FROM cc_payment_settings),"
    "       (SELECT count(*) FROM audit_events)"
)


def test_the_seed_lets_ascensores_delta_send_reminders_locally(sessions) -> None:
    with sessions() as session:
        seed_dev.seed(session)
        seed_dev.seed_reminders(session)
        first = session.execute(text(COUNTS)).one()
        seed_dev.seed_reminders(session)
        again = session.execute(text(COUNTS)).one()
        sender = session.execute(
            text(
                "SELECT c.sender, c.phone_number_id FROM whatsapp_connections c "
                "JOIN tenants t ON t.id = c.tenant_id WHERE t.name = 'Ascensores Delta'"
            )
        ).one()

    assert tuple(first[:4]) == (1, 4, 1, 1)
    assert tuple(again) == tuple(first)
    assert tuple(sender) == ("log", "dev-cc-phone-1")
