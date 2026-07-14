"""
Example analytical queries over the archived Slack data.

These are intentionally simple, composable building blocks (each returns a
pandas DataFrame) rather than a fixed dashboard -- treat this as a starting
point for whatever analysis is actually wanted next (activity trends,
influence/response-time analysis, topic clustering, etc.).
"""

import re
from collections import Counter

import pandas as pd
from sqlalchemy import Engine

from slack_msg_reader.db.database import get_engine

# Tiny bilingual stopword list -- naive whitespace tokenization does not
# properly segment Japanese (no MeCab/Janome dependency here), so this is a
# rough signal, not real NLP. Swap in a real tokenizer for serious analysis.
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on", "for",
    "and", "or", "but", "this", "that", "it", "i", "you", "we", "です", "ます",
    "した", "して", "する", "こと", "これ", "それ", "ため", "よう", "また",
}
_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)


def _engine() -> Engine:
    return get_engine()


def messages_per_channel() -> pd.DataFrame:
    sql = """
        SELECT c.name AS channel, c.kind AS kind, COUNT(*) AS message_count
        FROM messages m
        JOIN channels c ON c.id = m.channel_id
        GROUP BY c.id
        ORDER BY message_count DESC
    """
    return pd.read_sql(sql, _engine())


def messages_per_user(channel_name: str | None = None) -> pd.DataFrame:
    sql = """
        SELECT u.display_name AS user, COUNT(*) AS message_count
        FROM messages m
        JOIN users u ON u.id = m.user_id
        JOIN channels c ON c.id = m.channel_id
        {where}
        GROUP BY u.id
        ORDER BY message_count DESC
    """
    params = {}
    where = ""
    if channel_name:
        where = "WHERE c.name = :channel_name"
        params["channel_name"] = channel_name
    return pd.read_sql(sql.format(where=where), _engine(), params=params)


def activity_by_hour() -> pd.DataFrame:
    sql = """
        SELECT CAST(strftime('%H', posted_at) AS INTEGER) AS hour, COUNT(*) AS message_count
        FROM messages
        WHERE posted_at IS NOT NULL
        GROUP BY hour
        ORDER BY hour
    """
    return pd.read_sql(sql, _engine())


def activity_by_weekday() -> pd.DataFrame:
    # SQLite %w: 0=Sunday .. 6=Saturday
    sql = """
        SELECT CAST(strftime('%w', posted_at) AS INTEGER) AS weekday, COUNT(*) AS message_count
        FROM messages
        WHERE posted_at IS NOT NULL
        GROUP BY weekday
        ORDER BY weekday
    """
    return pd.read_sql(sql, _engine())


def reply_thread_leaderboard(limit: int = 20) -> pd.DataFrame:
    sql = """
        SELECT c.name AS channel, u.display_name AS user, m.text, m.reply_count, m.posted_at
        FROM messages m
        JOIN channels c ON c.id = m.channel_id
        LEFT JOIN users u ON u.id = m.user_id
        WHERE m.reply_count > 0
        ORDER BY m.reply_count DESC
        LIMIT :limit
    """
    return pd.read_sql(sql, _engine(), params={"limit": limit})


def reaction_leaderboard(limit: int = 20) -> pd.DataFrame:
    sql = """
        SELECT emoji, SUM(count) AS total_count
        FROM reactions
        GROUP BY emoji
        ORDER BY total_count DESC
        LIMIT :limit
    """
    return pd.read_sql(sql, _engine(), params={"limit": limit})


def keyword_search(keyword: str, limit: int = 50) -> pd.DataFrame:
    sql = """
        SELECT c.name AS channel, u.display_name AS user, m.posted_at, m.text
        FROM messages m
        JOIN channels c ON c.id = m.channel_id
        LEFT JOIN users u ON u.id = m.user_id
        WHERE m.text LIKE :pattern
        ORDER BY m.posted_at DESC
        LIMIT :limit
    """
    return pd.read_sql(sql, _engine(), params={"pattern": f"%{keyword}%", "limit": limit})


def top_words(top_n: int = 30, min_len: int = 2) -> pd.DataFrame:
    """Naive whitespace-tokenized word frequency (see module docstring caveat)."""
    texts = pd.read_sql("SELECT text FROM messages", _engine())["text"]
    counter: Counter[str] = Counter()
    for text in texts:
        for token in _TOKEN_RE.findall(text.lower()):
            if len(token) < min_len or token in _STOPWORDS:
                continue
            counter[token] += 1
    return pd.DataFrame(counter.most_common(top_n), columns=["word", "count"])
