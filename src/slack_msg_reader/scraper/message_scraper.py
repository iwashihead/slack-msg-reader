import logging
import re
from datetime import datetime, timezone

from playwright.sync_api import Page

from slack_msg_reader.config import MAX_SCROLLS_PER_CHANNEL, SCROLL_WAIT_MS
from slack_msg_reader.scraper.parser import parse_visible_messages
from slack_msg_reader.scraper.selectors import MESSAGE_LIST_SCROLL_CONTAINER

log = logging.getLogger(__name__)

_TEAM_ID_RE = re.compile(r"/client/(T[A-Z0-9]+)/")


def current_team_id(page: Page) -> str:
    m = _TEAM_ID_RE.search(page.url)
    if not m:
        raise RuntimeError(f"Could not extract team id from URL: {page.url}")
    return m.group(1)


def navigate_to_channel(page: Page, team_id: str, channel_id: str) -> None:
    page.goto(f"https://app.slack.com/client/{team_id}/{channel_id}")
    page.wait_for_selector(MESSAGE_LIST_SCROLL_CONTAINER, timeout=15000)
    page.wait_for_timeout(500)


def _scroll_container_height(page: Page) -> int:
    return page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            return el ? el.scrollHeight : -1;
        }""",
        MESSAGE_LIST_SCROLL_CONTAINER,
    )


def _scroll_to_top(page: Page) -> None:
    page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (el) el.scrollTop = 0;
        }""",
        MESSAGE_LIST_SCROLL_CONTAINER,
    )


def ts_to_datetime(ts: str) -> datetime:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def collect_channel_messages(
    page: Page, last_known_ts: str | None, seed_sender: str | None = None
) -> list[dict]:
    """Scrolls up through a channel's history, collecting messages newer than last_known_ts.

    If last_known_ts is None, walks all the way to the top of the channel
    (full history, bounded by MAX_SCROLLS_PER_CHANNEL as a safety cap).
    Returns messages sorted oldest-first, deduplicated by ts, with `sender`
    forward-filled (Slack omits the sender element on grouped/consecutive
    messages -- see parser.py). `seed_sender` should be the sender of the
    last message already stored for this channel, so the very first message
    in this batch can inherit it if it turns out to be a grouped
    continuation of a message from a prior `collect` run.
    """
    collected: dict[str, dict] = {}
    previous_height = -1

    for scroll_attempt in range(MAX_SCROLLS_PER_CHANNEL):
        for msg in parse_visible_messages(page):
            if last_known_ts is not None and msg["ts"] <= last_known_ts:
                continue
            collected[msg["ts"]] = msg

        height = _scroll_container_height(page)
        if height == previous_height:
            log.debug("Reached top of channel history after %d scrolls", scroll_attempt)
            break
        previous_height = height

        if last_known_ts is not None:
            oldest_ts = min((m["ts"] for m in collected.values()), default=None)
            if oldest_ts is not None and oldest_ts <= last_known_ts:
                break

        _scroll_to_top(page)
        page.wait_for_timeout(SCROLL_WAIT_MS)
    else:
        log.warning("Hit MAX_SCROLLS_PER_CHANNEL safety cap; history may be incomplete")

    ordered = sorted(collected.values(), key=lambda m: m["ts"])
    last_sender = seed_sender
    for msg in ordered:
        if msg["sender"] is None:
            msg["sender"] = last_sender or "unknown"
        else:
            last_sender = msg["sender"]
    return ordered
