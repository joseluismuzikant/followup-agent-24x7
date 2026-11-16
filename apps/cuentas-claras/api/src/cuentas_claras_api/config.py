"""Cuentas Claras's settings: the platform's loader with this product's spec. Its panel,
CORS origins, email sender and Meta app (CUENTAS_CLARAS_META_APP_ID, _META_APP_SECRET,
_WHATSAPP_VERIFY_TOKEN, _META_EMBEDDED_SIGNUP_CONFIG_ID) are read with the CUENTAS_CLARAS_
prefix (inmo24x7 reads the plain names): Cuentas Claras has its own Meta app. No agent model
is required yet (Day 10)."""

from functools import lru_cache

from followup_platform.settings import ConfigurationError, ProductSpec, Settings, load_settings

from .product import PRODUCT

SPEC = ProductSpec(
    product=PRODUCT,
    env_prefix="CUENTAS_CLARAS_",
    default_panel_url="http://localhost:5175",
    default_cors_origins="http://localhost:5175,http://localhost:5176",
    requires_llm=False,
    requires_whatsapp=True,
    default_email_from="Cuentas Claras <avisos@cuentasclaras.local>",
)

__all__ = ["SPEC", "ConfigurationError", "Settings", "get_settings"]


@lru_cache
def get_settings() -> Settings:
    return load_settings(SPEC)
