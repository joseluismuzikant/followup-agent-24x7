"""Cuentas Claras reads its own Meta app (CUENTAS_CLARAS_META_*), never inmo24x7's, and in
production it needs one: reminders go out on WhatsApp."""

import pytest
from cuentas_claras_api.config import SPEC, ConfigurationError
from followup_platform.settings import load_settings

PRODUCTION = {
    "APP_ENV": "production",
    "DATABASE_URL": "postgresql+psycopg://u:p@db.example.com:5432/postgres",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_JWT_SECRET": "jwt-secret",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
    "CUENTAS_CLARAS_CORS_ORIGINS": "https://cuentasclaras.example.com",
    "CUENTAS_CLARAS_PANEL_URL": "https://cuentasclaras.example.com",
    "CUENTAS_CLARAS_EMAIL_FROM": "Cuentas Claras <avisos@example.com>",
    "SMTP_HOST": "smtp.example.com",
    "SUPPORT_EMAIL": "soporte@example.com",
    "WHATSAPP_SENDER": "cloud",
    "TOKEN_ENCRYPTION_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    "CUENTAS_CLARAS_META_APP_ID": "cc-app-id",
    "CUENTAS_CLARAS_META_APP_SECRET": "cc-app-secret",
    "CUENTAS_CLARAS_WHATSAPP_VERIFY_TOKEN": "cc-verify-token",
    "CUENTAS_CLARAS_META_EMBEDDED_SIGNUP_CONFIG_ID": "cc-config-id",
    # inmo24x7's app: never read by Cuentas Claras.
    "META_APP_ID": "inmo-app-id",
    "META_APP_SECRET": "inmo-app-secret",
    "WHATSAPP_VERIFY_TOKEN": "inmo-verify-token",
}


@pytest.fixture
def production(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("REHEARSAL", raising=False)
    for name, value in PRODUCTION.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def test_cuentas_claras_uses_its_own_meta_app(production) -> None:
    settings = load_settings(SPEC)

    assert settings.meta_app_id == "cc-app-id"
    assert settings.meta_app_secret == "cc-app-secret"
    assert settings.whatsapp_verify_token == "cc-verify-token"
    assert settings.meta_embedded_signup_config_id == "cc-config-id"


@pytest.mark.parametrize(
    "name",
    [
        "CUENTAS_CLARAS_META_APP_SECRET",
        "CUENTAS_CLARAS_WHATSAPP_VERIFY_TOKEN",
        "CUENTAS_CLARAS_META_APP_ID",
        "CUENTAS_CLARAS_META_EMBEDDED_SIGNUP_CONFIG_ID",
    ],
)
def test_production_needs_the_cuentas_claras_meta_app(production, name: str) -> None:
    production.delenv(name)

    with pytest.raises(ConfigurationError, match=name):
        load_settings(SPEC)
