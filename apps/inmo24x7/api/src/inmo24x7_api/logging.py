"""Moved to followup_platform.logging (shared by every product API)."""

from followup_platform.logging import JsonFormatter, configure_logging

__all__ = ["JsonFormatter", "configure_logging"]
