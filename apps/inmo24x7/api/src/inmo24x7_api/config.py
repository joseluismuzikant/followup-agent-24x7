"""inmo24x7's settings: the platform's loader (followup_platform.settings) with inmo24x7's
product spec. inmo24x7 reads every variable without a prefix, as before there were two
products."""

from functools import lru_cache

from followup_platform.settings import ConfigurationError, ProductSpec, Settings, load_settings

from .product import PRODUCT

SPEC = ProductSpec(product=PRODUCT)

__all__ = ["SPEC", "ConfigurationError", "Settings", "get_settings"]


@lru_cache
def get_settings() -> Settings:
    return load_settings(SPEC)
