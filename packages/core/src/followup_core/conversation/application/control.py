"""Takeover: a person from the team takes a conversation, answers it, and gives it back.

Every use case here takes the same per-thread lock as an agent turn. A takeover that races
a running turn waits for it to finish; any turn after it sees `control = human` and only
stores the visitor's messages.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from ..domain.errors import ConversationNotTakenError, InvalidMessageError, ThreadNotFoundError
from ..domain.repositories import MessageRepository, ThreadLock, ThreadRepository
from ..domain.thread import (
    Author,
    Direction,
    Message,
    Thread,
    release,
    system_event,
    take_over,
)
from .threads import Clock, utc_now

MAX_TEAM_MESSAGE_LENGTH = 4096


@dataclass(frozen=True, slots=True)
class Actor:
    """The person acting, as the transcript names them."""

    profile_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class ControlChange:
    thread: Thread
    # None when nothing changed (releasing a thread the agent already has).
    event: Message | None


class _Locked:
    def __init__(
        self,
        threads: ThreadRepository,
        messages: MessageRepository,
        lock: ThreadLock,
        clock: Clock = utc_now,
    ) -> None:
        self._threads = threads
        self._messages = messages
        self._lock = lock
        self._clock = clock

    def _locked_thread(self, thread_id: UUID) -> Thread:
        thread = self._threads.get_by_id(thread_id)
        if thread is None:
            raise ThreadNotFoundError(str(thread_id))
        self._lock.acquire(thread.key)
        # Read again under the lock: a turn or another takeover may have just committed.
        current = self._threads.get_by_key(thread.key)
        if current is None:
            raise ThreadNotFoundError(str(thread_id))
        return current


class TakeOverThread(_Locked):
    def execute(self, thread_id: UUID, actor: Actor) -> ControlChange:
        thread = self._locked_thread(thread_id)
        if thread.is_taken_over and thread.controlled_by_profile_id == actor.profile_id:
            return ControlChange(thread, None)
        now = self._clock()
        taken, event = take_over(thread, actor.profile_id, actor.name, now)
        self._threads.set_control(taken)
        self._messages.append(event)
        self._threads.touch(thread.id, now)
        return ControlChange(taken, event)


class ReleaseThread(_Locked):
    def execute(self, thread_id: UUID, actor: Actor) -> ControlChange:
        thread = self._locked_thread(thread_id)
        now = self._clock()
        released, event = release(thread, actor.name, now)
        if event is None:
            return ControlChange(thread, None)
        self._threads.set_control(released)
        self._messages.append(event)
        self._threads.touch(thread.id, now)
        return ControlChange(released, event)


class AddTeamMessage(_Locked):
    """Stores a message from the team to the visitor. The channel sends it (the product
    decides how); here it is only written to the transcript."""

    def execute(
        self,
        thread_id: UUID,
        actor: Actor,
        text: str,
        *,
        require_control: bool = True,
        payload: Mapping[str, Any] | None = None,
    ) -> Message:
        cleaned = text.strip()
        if not cleaned or len(cleaned) > MAX_TEAM_MESSAGE_LENGTH:
            raise InvalidMessageError(
                f"A message must have 1 to {MAX_TEAM_MESSAGE_LENGTH} characters."
            )
        thread = self._locked_thread(thread_id)
        if require_control and not thread.is_taken_over:
            raise ConversationNotTakenError(str(thread_id))
        now = self._clock()
        message = Message(
            uuid4(),
            thread.id,
            Direction.OUTBOUND,
            Author.HUMAN,
            cleaned,
            now,
            dict(payload) if payload else None,
            author_profile_id=actor.profile_id,
        )
        self._messages.append(message)
        self._threads.touch(thread.id, now)
        return message


class AddSystemEvent(_Locked):
    """A centered event in the transcript ("Ana confirmó la visita"), under the thread lock."""

    def execute(self, thread_id: UUID, text: str) -> Message:
        thread = self._locked_thread(thread_id)
        now = self._clock()
        event = system_event(thread, text, now)
        self._messages.append(event)
        self._threads.touch(thread.id, now)
        return event
