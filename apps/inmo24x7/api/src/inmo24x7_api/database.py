"""inmo24x7's database (followup_platform.database)."""

from followup_platform.database import build_database, session_dependency

from .config import get_settings

DATABASE = build_database(get_settings())
engine = DATABASE.engine
SessionLocal = DATABASE.sessions
usage_engine = DATABASE.usage_engine
UsageSessionLocal = DATABASE.usage_sessions
get_session = session_dependency(SessionLocal)
