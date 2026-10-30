from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc))


def _now():
    return datetime.now(timezone.utc)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(64), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="paid")
    created: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(64), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    created: Mapped[datetime] = mapped_column(DateTime, default=_now)


class JournalEntry(Base):
    """Append-only intake log, written first. It is the source of truth for replaying lost orders and payments."""
    __tablename__ = "order_journal"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(64), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    created: Mapped[datetime] = mapped_column(DateTime, default=_now)


class QueueMessage(Base):
    """A message waiting for the worker. Bounded by QUEUE_MAX_DEPTH."""
    __tablename__ = "queue_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    msg_ref: Mapped[str] = mapped_column(String(64), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    created: Mapped[datetime] = mapped_column(DateTime, default=_now)


class QueueDone(Base):
    """A message the worker has processed. Unique by msg_ref, so replays cannot be processed twice."""
    __tablename__ = "queue_done"

    id: Mapped[int] = mapped_column(primary_key=True)
    msg_ref: Mapped[str] = mapped_column(String(64), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    processed: Mapped[datetime] = mapped_column(DateTime, default=_now)


class QueueJournal(Base):
    """Append-only intake log for queue messages, written before the queue. The source of truth for replays."""
    __tablename__ = "queue_journal"

    id: Mapped[int] = mapped_column(primary_key=True)
    msg_ref: Mapped[str] = mapped_column(String(64), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    created: Mapped[datetime] = mapped_column(DateTime, default=_now)
