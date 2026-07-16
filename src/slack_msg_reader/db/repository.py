from sqlalchemy import select
from sqlalchemy.orm import Session

from slack_msg_reader.db.models import Channel, Message, Reaction, User


def upsert_channel(session: Session, channel_id: str, name: str, kind: str) -> Channel:
    channel = session.get(Channel, channel_id)
    if channel is None:
        channel = Channel(id=channel_id, name=name, kind=kind)
        session.add(channel)
    else:
        channel.name = name
        channel.kind = kind
    return channel


def upsert_user(session: Session, user_id: str, display_name: str, real_name: str | None = None) -> User:
    user = session.get(User, user_id)
    if user is None:
        user = User(id=user_id, display_name=display_name, real_name=real_name)
        session.add(user)
    else:
        user.display_name = display_name
        if real_name:
            user.real_name = real_name
    return user


def latest_ts_for_channel(session: Session, channel_id: str) -> str | None:
    """Highest known Slack message ts already stored for this channel (used to stop incremental scroll)."""
    row = session.execute(
        select(Message.ts)
        .where(Message.channel_id == channel_id)
        .order_by(Message.ts.desc())
        .limit(1)
    ).first()
    return row[0] if row else None


def latest_message_sender(session: Session, channel_id: str) -> tuple[str, str] | None:
    """(display_name, user_id) of whoever sent the most recent stored message
    in this channel, or None if the channel has no stored messages yet.

    Used to seed forward-fill when a new `collect` batch's first message
    turns out to be a grouped continuation of a message from a prior run.
    """
    row = session.execute(
        select(User.display_name, User.id)
        .join(Message, Message.user_id == User.id)
        .where(Message.channel_id == channel_id)
        .order_by(Message.ts.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def message_exists(session: Session, channel_id: str, ts: str) -> bool:
    return (
        session.execute(
            select(Message.id).where(Message.channel_id == channel_id, Message.ts == ts)
        ).first()
        is not None
    )


def insert_message(
    session: Session,
    channel_id: str,
    ts: str,
    user_id: str | None,
    text: str,
    thread_ts: str | None,
    is_thread_parent: bool,
    reply_count: int,
    posted_at,
    reactions: list[tuple[str, int]] | None = None,
) -> Message:
    message = Message(
        channel_id=channel_id,
        ts=ts,
        user_id=user_id,
        text=text,
        thread_ts=thread_ts,
        is_thread_parent=is_thread_parent,
        reply_count=reply_count,
        posted_at=posted_at,
    )
    session.add(message)
    session.flush()  # populate message.id
    # Defensive dedup: `reactions` has a UNIQUE(message_id, emoji) constraint,
    # and a duplicate emoji name here would abort the whole batch insert (a
    # single scrape glitch shouldn't lose every message collected this run).
    merged: dict[str, int] = {}
    for emoji, count in reactions or []:
        merged[emoji] = merged.get(emoji, 0) + count
    for emoji, count in merged.items():
        session.add(Reaction(message_id=message.id, emoji=emoji, count=count))
    return message
