"""Embedded Signup progress for one tenant. Each step is stored as it completes, so a
failure (Meta down, a PIN problem, ...) can be retried from that step without asking the
customer to go through Meta's popup again: the business token is kept, encrypted."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class SignupStep(StrEnum):
    STARTED = "started"  # Meta sent the ids; the code is not exchanged yet
    EXCHANGED = "exchanged"  # we have the business token
    SUBSCRIBED = "subscribed"  # our app receives the WABA's webhooks
    REGISTERED = "registered"  # the number is registered for the Cloud API
    CONNECTED = "connected"  # the connection is saved


STEP_ORDER: Sequence[SignupStep] = tuple(SignupStep)


def reached(current: SignupStep, step: SignupStep) -> bool:
    return STEP_ORDER.index(current) >= STEP_ORDER.index(step)


@dataclass(frozen=True, slots=True)
class Signup:
    tenant_id: UUID
    waba_id: str
    phone_number_id: str
    business_id: str | None
    step: SignupStep
    pin_encrypted: str
    updated_at: datetime
    token_encrypted: str | None = None
    last_error_code: str | None = None


class SignupRepository(Protocol):
    def get(self, tenant_id: UUID) -> Signup | None: ...

    def save(self, signup: Signup) -> None: ...
