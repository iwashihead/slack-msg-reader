"""
Exports archived messages into AI-friendly Markdown file(s): filtered by
channel/user/date range, grouped by channel so conversation threads stay
together, and split across multiple files only when needed to stay under a
per-file character budget (different models have very different context
limits, so this is left configurable rather than assumed).
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from slack_msg_reader.db.database import session_scope
from slack_msg_reader.db.models import Channel, Message, User

DEFAULT_MAX_CHARS = 300_000
DEFAULT_MAX_FILES = 10


@dataclass
class ChannelBlock:
    header: str
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.header + "".join(self.lines)

    @property
    def length(self) -> int:
        return len(self.header) + sum(len(line) for line in self.lines)


def _format_message_line(msg: Message) -> str:
    when = msg.posted_at.strftime("%Y-%m-%d %H:%M") if msg.posted_at else msg.ts
    sender = msg.user.display_name if msg.user else "unknown"
    text = msg.text.replace("\n", "\n  ")  # indent continuation lines under the bullet
    suffix_parts = []
    if msg.reply_count:
        suffix_parts.append(f"{msg.reply_count} replies")
    if msg.reactions:
        reacts = ", ".join(f"{r.emoji}×{r.count}" for r in msg.reactions)
        suffix_parts.append(f"reactions: {reacts}")
    suffix = f"  _({'; '.join(suffix_parts)})_" if suffix_parts else ""
    return f"- **{when}** {sender}: {text}{suffix}\n"


def _group_messages_into_blocks(messages: list[Message]) -> list[ChannelBlock]:
    """Groups already-fetched messages (assumed ordered by channel, then ts) into one block per channel."""
    blocks: dict[str, ChannelBlock] = {}
    order: list[str] = []
    for msg in messages:
        cid = msg.channel_id
        if cid not in blocks:
            blocks[cid] = ChannelBlock(header=f"## {msg.channel.name} ({msg.channel.kind})\n\n")
            order.append(cid)
        blocks[cid].lines.append(_format_message_line(msg))
    return [blocks[cid] for cid in order]


def fetch_channel_blocks(
    channel: str | None = None,
    user: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[ChannelBlock]:
    """Queries the archive and groups matching messages into one block per channel.

    Note `user` restricts to messages *sent by* that person -- for "every
    message in the channels a person took part in" (i.e. their side of a
    conversation plus everyone else's), see fetch_channel_blocks_for_participant.
    """
    with session_scope() as session:
        stmt = (
            select(Message)
            .join(Channel)
            .options(joinedload(Message.channel), joinedload(Message.user), joinedload(Message.reactions))
            .order_by(Channel.name, Message.ts.asc())
        )
        if channel:
            stmt = stmt.where(Channel.name == channel)
        if user:
            stmt = stmt.where(Message.user.has(display_name=user))
        if since:
            stmt = stmt.where(Message.posted_at >= since)
        if until:
            stmt = stmt.where(Message.posted_at <= until)

        messages = session.execute(stmt).unique().scalars().all()
        return _group_messages_into_blocks(messages)


def fetch_channel_blocks_for_participant(
    participant: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[ChannelBlock]:
    """Full-context export for one person: every message (from anyone) in every
    channel/DM where `participant` posted at least once during the window.

    Unlike fetch_channel_blocks(user=...), this deliberately does NOT filter
    messages down to that person's own -- understanding what someone was
    doing requires the other side of their conversations too.
    """
    with session_scope() as session:
        participant_channels_stmt = (
            select(Message.channel_id)
            .join(User, Message.user_id == User.id)
            .where(User.display_name == participant)
            .distinct()
        )
        if since:
            participant_channels_stmt = participant_channels_stmt.where(Message.posted_at >= since)
        if until:
            participant_channels_stmt = participant_channels_stmt.where(Message.posted_at <= until)

        channel_ids = session.execute(participant_channels_stmt).scalars().all()
        if not channel_ids:
            return []

        stmt = (
            select(Message)
            .join(Channel)
            .options(joinedload(Message.channel), joinedload(Message.user), joinedload(Message.reactions))
            .where(Message.channel_id.in_(channel_ids))
            .order_by(Channel.name, Message.ts.asc())
        )
        if since:
            stmt = stmt.where(Message.posted_at >= since)
        if until:
            stmt = stmt.where(Message.posted_at <= until)

        messages = session.execute(stmt).unique().scalars().all()
        return _group_messages_into_blocks(messages)


def _split_oversized_block(block: ChannelBlock, max_chars: int) -> list[str]:
    parts: list[str] = []
    current = [block.header]
    current_len = len(block.header)
    for line in block.lines:
        if current_len + len(line) > max_chars and current_len > len(block.header):
            parts.append("".join(current))
            continuation_header = block.header.rstrip("\n") + "  (continued)\n\n"
            current = [continuation_header]
            current_len = len(continuation_header)
        current.append(line)
        current_len += len(line)
    parts.append("".join(current))
    return parts


def pack_into_files(blocks: list[ChannelBlock], max_chars: int) -> list[str]:
    """Greedily bin-packs whole channel blocks into files under max_chars each.

    A single channel block larger than max_chars is split at message-line
    boundaries (never mid-message), repeating its header per continuation.
    """
    files: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current_parts, current_len
        if current_parts:
            files.append("".join(current_parts))
            current_parts = []
            current_len = 0

    for block in blocks:
        if block.length > max_chars:
            flush()
            files.extend(_split_oversized_block(block, max_chars))
            continue
        if current_len + block.length > max_chars and current_parts:
            flush()
        current_parts.append(block.text)
        current_len += block.length

    flush()
    return files


def chunk_blocks(blocks: list[ChannelBlock], max_chars: int, max_files: int) -> tuple[list[str], bool]:
    """Packs blocks into files, growing max_chars if needed to respect max_files.

    Returns (files, truncated_warning) -- truncated_warning is True if even
    after growing the per-file budget, the result still exceeds max_files
    (only happens if a single channel's continued blocks alone need more
    than max_files pieces).
    """
    files = pack_into_files(blocks, max_chars)
    if len(files) <= max_files:
        return files, False

    total_len = sum(b.length for b in blocks)
    grown_max_chars = max(max_chars, -(-total_len // max_files))  # ceil division
    files = pack_into_files(blocks, grown_max_chars)
    return files, len(files) > max_files


def write_blocks(
    blocks: list[ChannelBlock],
    output_dir: Path,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_files: int = DEFAULT_MAX_FILES,
    base_name: str = "slack_export",
) -> tuple[list[Path], bool]:
    """Chunks pre-fetched blocks and writes them to output_dir. Shared by
    write_export() and report.generate_report()."""
    if not blocks:
        return [], False

    files_content, truncated = chunk_blocks(blocks, max_chars, max_files)

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    if len(files_content) == 1:
        path = output_dir / f"{base_name}.md"
        path.write_text(files_content[0], encoding="utf-8")
        paths.append(path)
    else:
        for i, content in enumerate(files_content, start=1):
            path = output_dir / f"{base_name}_{i:02d}_of_{len(files_content):02d}.md"
            path.write_text(content, encoding="utf-8")
            paths.append(path)

    return paths, truncated


def write_export(
    output_dir: Path,
    channel: str | None = None,
    user: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_files: int = DEFAULT_MAX_FILES,
    base_name: str = "slack_export",
) -> tuple[list[Path], bool]:
    blocks = fetch_channel_blocks(channel=channel, user=user, since=since, until=until)
    return write_blocks(blocks, output_dir, max_chars=max_chars, max_files=max_files, base_name=base_name)
