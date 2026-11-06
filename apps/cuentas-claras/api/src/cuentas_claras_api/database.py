"""Cuentas Claras's database (followup_platform.database)."""

from followup_platform.database import build_database, session_dependency

from .config import get_settings

DATABASE = build_database(get_settings())
SessionLocal = DATABASE.sessions
get_session = session_dependency(SessionLocal)
