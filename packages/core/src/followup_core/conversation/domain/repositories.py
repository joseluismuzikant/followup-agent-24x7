from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from .thread import Channel, Message, Thread, ThreadKey


class ThreadRepository(Protocol):
    def get_by_key(self, key: ThreadKey) -> Thread | None: ...

    def count_started_by(self, tenant_id: UUID, channel: Channel, profile_id: UUID) -> int: ...

    def add(self, thread: Thread) -> None: ...

    def touch(self, thread_id: UUID, last_message_at: datetime) -> None: ...


class MessageRepository(Protocol):
    def append(self, message: Message) -> None: ...

    def list_for_thread(self, thread_id: UUID) -> Sequence[Message]:
        """Oldest first."""
        ...

    def count_inbound_since(self, tenant_id: UUID, channel: Channel, since: datetime) -> int: ...


class ThreadLock(Protocol):
    def acquire(self, key: ThreadKey) -> None:
        """Blocks until no other turn holds the key; released when the transaction ends."""
        ...
