from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from followup_core.identity.infrastructure.models import ProfileModel

from ..domain.thread import (
    Author,
    Channel,
    Direction,
    Message,
    Thread,
    ThreadKey,
    ThreadStatus,
)
from .models import MessageModel, ThreadModel


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _thread_to_domain(model: ThreadModel) -> Thread:
    return Thread(
        id=model.id,
        key=ThreadKey(model.tenant_id, Channel(model.channel), model.visitor_id),
        agent_config_version=model.agent_config_version,
        status=ThreadStatus(model.status),
        created_at=_aware(model.created_at),
        last_message_at=_aware(model.last_message_at) if model.last_message_at else None,
        started_by_profile_id=model.started_by_profile_id,
    )


class SqlAlchemyThreadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_key(self, key: ThreadKey) -> Thread | None:
        model = self._session.scalars(
            select(ThreadModel).where(ThreadModel.key == str(key))
        ).first()
        return _thread_to_domain(model) if model else None

    def count_started_by(self, tenant_id: UUID, channel: Channel, profile_id: UUID) -> int:
        statement = self._started_by(tenant_id, channel, profile_id).subquery()
        return self._session.scalar(select(func.count()).select_from(statement)) or 0

    def add(self, thread: Thread) -> None:
        self._session.add(
            ThreadModel(
                id=thread.id,
                key=str(thread.key),
                tenant_id=thread.tenant_id,
                channel=thread.channel.value,
                visitor_id=thread.visitor_id,
                agent_config_version=thread.agent_config_version,
                status=thread.status.value,
                started_by_profile_id=thread.started_by_profile_id,
                created_at=thread.created_at,
                last_message_at=thread.last_message_at,
            )
        )
        self._session.flush()

    def touch(self, thread_id: UUID, last_message_at: datetime) -> None:
        self._session.execute(
            update(ThreadModel)
            .where(ThreadModel.id == thread_id)
            .values(last_message_at=last_message_at)
        )

    @staticmethod
    def _started_by(tenant_id: UUID, channel: Channel, profile_id: UUID):
        return select(ThreadModel).where(
            ThreadModel.tenant_id == tenant_id,
            ThreadModel.channel == channel.value,
            ThreadModel.started_by_profile_id == profile_id,
        )


class SqlAlchemyMessageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, message: Message) -> None:
        self._session.add(
            MessageModel(
                id=message.id,
                thread_id=message.thread_id,
                direction=message.direction.value,
                author=message.author.value,
                text=message.text,
                payload=message.payload,
                trace_run_id=message.trace_run_id,
                created_at=message.created_at,
            )
        )
        self._session.flush()

    def list_for_thread(self, thread_id: UUID) -> Sequence[Message]:
        models = self._session.scalars(
            select(MessageModel)
            .where(MessageModel.thread_id == thread_id)
            .order_by(MessageModel.seq)
        ).all()
        return [
            Message(
                id=model.id,
                thread_id=model.thread_id,
                direction=Direction(model.direction),
                author=Author(model.author),
                text=model.text,
                created_at=_aware(model.created_at),
                payload=model.payload,
                trace_run_id=model.trace_run_id,
            )
            for model in models
        ]

    def count_inbound_since(self, tenant_id: UUID, channel: Channel, since: datetime) -> int:
        statement = (
            select(func.count())
            .select_from(MessageModel)
            .join(ThreadModel, ThreadModel.id == MessageModel.thread_id)
            .where(
                ThreadModel.tenant_id == tenant_id,
                ThreadModel.channel == channel.value,
                MessageModel.direction == Direction.INBOUND.value,
                MessageModel.created_at >= since,
            )
        )
        return self._session.scalar(statement) or 0


class PostgresAdvisoryThreadLock:
    """Serializes turns per thread with a transaction-level advisory lock."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def acquire(self, key: ThreadKey) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": str(key)}
        )


class SqlAlchemyConversationFacts:
    """Setup facts owned by the Conversation context."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def agent_tested(self, tenant_id: UUID) -> bool:
        """A member of the tenant sent at least one simulator message.

        Platform admins testing from the backoffice belong to another tenant, so their
        threads do not count.
        """
        statement = (
            select(MessageModel.id)
            .join(ThreadModel, ThreadModel.id == MessageModel.thread_id)
            .join(ProfileModel, ProfileModel.id == ThreadModel.started_by_profile_id)
            .where(
                ThreadModel.tenant_id == tenant_id,
                ThreadModel.channel == Channel.SIMULATOR.value,
                ProfileModel.tenant_id == tenant_id,
                MessageModel.direction == Direction.INBOUND.value,
            )
            .limit(1)
        )
        return self._session.scalar(statement) is not None
