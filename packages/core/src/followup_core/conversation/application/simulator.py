"""The simulator channel: each profile has threads numbered 1..n per tenant, and the current
one is n; Reiniciar opens n + 1. Visitor ids look like "{profile_id}.{n}"."""

from datetime import datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from ..domain.errors import SimulatorLimitReachedError
from ..domain.repositories import MessageRepository, ThreadRepository
from ..domain.thread import Channel, Thread, ThreadKey
from .ports import BusinessContextSource
from .threads import (
    Clock,
    GetThread,
    HandledTurn,
    HandleIncomingMessage,
    StartNewThread,
    ThreadView,
    utc_now,
)


def simulator_key(tenant_id: UUID, profile_id: UUID, number: int) -> ThreadKey:
    return ThreadKey(tenant_id, Channel.SIMULATOR, f"{profile_id}.{number}")


class SimulatorThreads:
    def __init__(self, threads: ThreadRepository) -> None:
        self._threads = threads

    def _count(self, tenant_id: UUID, profile_id: UUID) -> int:
        return self._threads.count_started_by(tenant_id, Channel.SIMULATOR, profile_id)

    def current_key(self, tenant_id: UUID, profile_id: UUID) -> ThreadKey:
        return simulator_key(tenant_id, profile_id, max(self._count(tenant_id, profile_id), 1))

    def next_key(self, tenant_id: UUID, profile_id: UUID) -> ThreadKey:
        return simulator_key(tenant_id, profile_id, self._count(tenant_id, profile_id) + 1)


class GetSimulator:
    def __init__(self, threads: ThreadRepository, get_thread: GetThread) -> None:
        self._threads = SimulatorThreads(threads)
        self._get_thread = get_thread

    def execute(self, tenant_id: UUID, profile_id: UUID) -> ThreadView:
        return self._get_thread.execute(tenant_id, self._threads.current_key(tenant_id, profile_id))


class SendSimulatorMessage:
    def __init__(
        self,
        threads: ThreadRepository,
        messages: MessageRepository,
        handle: HandleIncomingMessage,
        business: BusinessContextSource,
        daily_limit: int,
        clock: Clock = utc_now,
    ) -> None:
        self._threads = SimulatorThreads(threads)
        self._messages = messages
        self._handle = handle
        self._business = business
        self._daily_limit = daily_limit
        self._clock = clock

    def execute(self, tenant_id: UUID, profile_id: UUID, text: str) -> HandledTurn:
        timezone = ZoneInfo(self._business(tenant_id).timezone)
        start_of_day = datetime.combine(self._clock().astimezone(timezone).date(), time(), timezone)
        sent_today = self._messages.count_inbound_since(tenant_id, Channel.SIMULATOR, start_of_day)
        if sent_today >= self._daily_limit:
            raise SimulatorLimitReachedError("The tenant used all of today's simulator messages.")
        key = self._threads.current_key(tenant_id, profile_id)
        return self._handle.execute(key, text, started_by_profile_id=profile_id)


class ResetSimulator:
    def __init__(
        self, threads: ThreadRepository, start: StartNewThread, get_thread: GetThread
    ) -> None:
        self._threads = SimulatorThreads(threads)
        self._start = start
        self._get_thread = get_thread

    def execute(self, tenant_id: UUID, profile_id: UUID) -> ThreadView:
        thread: Thread = self._start.execute(
            self._threads.next_key(tenant_id, profile_id), started_by_profile_id=profile_id
        )
        return self._get_thread.execute(tenant_id, thread.key)
