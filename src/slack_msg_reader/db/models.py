from datetime import datetime, timezone

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    DateTime,
    Boolean,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # Slack channel id, or synthetic id for DMs
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # public_channel | private_channel | dm | mpim
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship(back_populates="channel")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # Slack user id if resolvable, else name-derived key
    display_name: Mapped[str] = mapped_column(String)
    real_name: Mapped[str | None] = mapped_column(String, nullable=True)

    messages: Mapped[list["Message"]] = relationship(back_populates="user")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("channel_id", "ts", name="uq_message_channel_ts"),
        Index("ix_message_channel_ts", "channel_id", "ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    ts: Mapped[str] = mapped_column(String)  # Slack message timestamp, e.g. "1699999999.000100"
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    thread_ts: Mapped[str | None] = mapped_column(String, nullable=True)  # set if this is a reply
    is_thread_parent: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    channel: Mapped["Channel"] = relationship(back_populates="messages")
    user: Mapped["User | None"] = relationship(back_populates="messages")
    reactions: Mapped[list["Reaction"]] = relationship(back_populates="message", cascade="all, delete-orphan")


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("message_id", "emoji", name="uq_reaction_message_emoji"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"))
    emoji: Mapped[str] = mapped_column(String)
    count: Mapped[int] = mapped_column(Integer, default=0)

    message: Mapped["Message"] = relationship(back_populates="reactions")
