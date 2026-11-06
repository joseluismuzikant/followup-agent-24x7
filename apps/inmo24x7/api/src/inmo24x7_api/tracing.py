"""LangSmith tracing (moved to followup_platform.tracing); inmo24x7 names its turns
"inmo24x7.lead_turn"."""

from followup_core.conversation.infrastructure.langgraph_runtime import TurnTracing
from followup_platform.tracing import (
    CLIENT_TIMEOUT_MS,
    DNI,
    EMAIL,
    PHONE,
    Tracing,
    TracingConfigError,
    agent,
    anonymize,
    build_tracing,
    flush,
    project_name,
    trace_url,
)
from followup_platform.tracing import turn_tracing as _turn_tracing

from .config import Settings

RUN_NAME = "inmo24x7.lead_turn"

__all__ = [
    "CLIENT_TIMEOUT_MS",
    "DNI",
    "EMAIL",
    "PHONE",
    "RUN_NAME",
    "Tracing",
    "TracingConfigError",
    "agent",
    "anonymize",
    "build_tracing",
    "flush",
    "project_name",
    "trace_url",
    "turn_tracing",
]


def turn_tracing(tracing: Tracing | None, settings: Settings) -> TurnTracing | None:
    return _turn_tracing(tracing, settings, RUN_NAME)
