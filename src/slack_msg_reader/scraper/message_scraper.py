import logging
import re
from datetime import datetime, timezone

from playwright.sync_api import Page

from slack_msg_reader.config import MAX_SCROLLS_PER_CHANNEL, SCROLL_WAIT_MS
from slack_msg_reader.scraper.parser import parse_visible_messages
from slack_msg_reader.scraper.selectors import (
    MESSAGE_LIST_SCROLL_CONTAINER,
    MESSAGE_THREAD_REPLY_BAR,
    THREAD_CLOSE_BUTTON,
    THREAD_PANEL,
)

log = logging.getLogger(__name__)

_TEAM_ID_RE = re.compile(r"/client/([A-Za-z0-9]+)(?:[/?#]|$)")


def current_team_id(page: Page) -> str:
    m = _TEAM_ID_RE.search(page.url)
    if not m:
        raise RuntimeError(f"Could not extract team id from URL: {page.url}")
    return m.group(1)


def navigate_to_channel(page: Page, team_id: str, channel_id: str) -> None:
    page.goto(f"https://app.slack.com/client/{team_id}/{channel_id}")
    page.wait_for_selector(MESSAGE_LIST_SCROLL_CONTAINER, timeout=15000)
    page.wait_for_timeout(500)


def ensure_not_on_search_page(page: Page) -> None:
    """The sidebar's channel list isn't even in the DOM while the tab is
    showing Slack's own /search results view (confirmed live: `slack collect
    --user` leaves the tab there when it's done, and a plain `slack collect`
    run right after finds 0 channels).

    Navigating to the bare team root (`/client/TEAM_ID`) does *not* fix this
    -- confirmed live that Slack's own client-side router just redirects
    straight back to /search, since it persists "last viewed" per team and
    search was it. `page.go_back()` doesn't help either, for the same
    reason. What does work: pressing Escape (dismisses the search
    autocomplete overlay, which otherwise can intercept the next click --
    see search.py's docstring for the same failure mode) and then clicking
    the left rail's Home button, which Slack treats as a real navigation
    away from search rather than a route it silently overrides.
    """
    if "/search" not in page.url:
        return
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    home_btn = page.query_selector('[data-qa="tab_rail_home_button"]')
    if home_btn is None:
        log.warning("Stuck on /search and couldn't find the home rail button to escape it")
        return
    try:
        home_btn.click(timeout=10000)
    except Exception:
        log.warning("Clicking the home rail button to leave /search failed", exc_info=True)
        return
    page.wait_for_timeout(1500)


def _scroll_container_height(page: Page, scope_selector: str | None = None) -> int:
    return page.evaluate(
        """([containerSel, scopeSel]) => {
            const root = scopeSel ? document.querySelector(scopeSel) : document;
            const el = root ? root.querySelector(containerSel) : null;
            return el ? el.scrollHeight : -1;
        }""",
        [MESSAGE_LIST_SCROLL_CONTAINER, scope_selector],
    )


def _scroll_to_top(page: Page, scope_selector: str | None = None) -> None:
    page.evaluate(
        """([containerSel, scopeSel]) => {
            const root = scopeSel ? document.querySelector(scopeSel) : document;
            const el = root ? root.querySelector(containerSel) : null;
            if (el) el.scrollTop = 0;
        }""",
        [MESSAGE_LIST_SCROLL_CONTAINER, scope_selector],
    )


def ts_to_datetime(ts: str) -> datetime:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def datetime_to_ts(dt: datetime) -> str:
    """Inverse of ts_to_datetime -- produces a string that sorts/compares
    correctly against real Slack ts strings (both have a 10-digit integer
    part for any date in the 2001-2286 range, so plain string comparison
    matches numeric comparison)."""
    return f"{dt.timestamp():.6f}"


def collect_thread_replies(
    page: Page,
    parent_ts: str,
    seed_sender: str | None = None,
    seed_sender_id: str | None = None,
    max_scrolls: int = MAX_SCROLLS_PER_CHANNEL,
) -> list[dict]:
    """Opens the thread for the message at parent_ts, scrolls to load every
    reply, and returns them (oldest-first, sender forward-filled, each
    tagged with thread_ts=parent_ts). Closes the thread panel before
    returning.

    Returns [] rather than raising if the thread can't be opened (row no
    longer rendered, DOM changed, etc.) -- one bad thread shouldn't abort
    the whole channel collection.
    """
    container = page.query_selector(f'[data-qa="message_container"][data-msg-ts="{parent_ts}"]')
    if container is None:
        log.warning("Could not find message container for thread parent ts=%s (may have scrolled past it)", parent_ts)
        return []

    reply_button = container.query_selector(MESSAGE_THREAD_REPLY_BAR)
    if reply_button is None:
        return []

    try:
        reply_button.click()
        page.wait_for_selector(THREAD_PANEL, timeout=20000)
    except Exception:
        log.warning("Could not open thread for ts=%s -- skipping this thread, continuing collection", parent_ts, exc_info=True)
        return []
    page.wait_for_timeout(400)

    collected: dict[str, dict] = {}
    previous_height = -1
    for _ in range(max_scrolls):
        for msg in parse_visible_messages(page, root_selector=THREAD_PANEL):
            if msg["ts"] == parent_ts:
                continue  # the flexpane repeats the parent message at the top
            collected[msg["ts"]] = msg

        height = _scroll_container_height(page, scope_selector=THREAD_PANEL)
        if height == previous_height:
            break
        previous_height = height
        _scroll_to_top(page, scope_selector=THREAD_PANEL)
        page.wait_for_timeout(SCROLL_WAIT_MS)

    try:
        close_btn = page.query_selector(THREAD_CLOSE_BUTTON)
        if close_btn:
            close_btn.click()
        # Generous wait: right after closing, the main channel view briefly
        # re-renders with stale/duplicate rows for the parent message
        # (confirmed live -- its reply_bar_count transiently read 0 instead
        # of the real count in that window), so give the close animation
        # room to fully settle before the caller re-scans the main channel.
        page.wait_for_timeout(700)
    except Exception:
        pass

    ordered = sorted(collected.values(), key=lambda m: m["ts"])
    last_sender, last_sender_id = seed_sender, seed_sender_id
    for msg in ordered:
        if msg["sender"] is None:
            msg["sender"] = last_sender or "unknown"
            msg["sender_id"] = last_sender_id
        else:
            last_sender, last_sender_id = msg["sender"], msg["sender_id"]
        msg["thread_ts"] = parent_ts
        msg["reply_count"] = 0  # Slack threads don't nest further

    return ordered


def collect_channel_messages(
    page: Page,
    last_known_ts: str | None,
    seed_sender: str | None = None,
    seed_sender_id: str | None = None,
    since_ts: str | None = None,
    until_ts: str | None = None,
    collect_threads: bool = True,
) -> list[dict]:
    """Scrolls up through a channel's history, collecting messages newer than
    the effective floor (see below), optionally also collecting each
    message's thread replies inline while its row is still rendered
    (waiting until after the whole channel is scrolled risks the row having
    been unmounted by virtualization by then).

    - `last_known_ts`: the latest ts already stored in the DB for this
      channel (incremental sync boundary). None on a first/--full-history run.
    - `since_ts`: an explicit user-requested lower bound, independent of
      what's already stored -- e.g. "don't bother going back further than
      30 days" even on a full-history run. The effective floor is the
      *later* (more restrictive) of last_known_ts and since_ts.
    - `until_ts`: skip messages newer than this (upper bound). Does not
      reduce how far up we need to scroll, since Slack always renders a
      channel starting from its newest message.

    Returns messages sorted oldest-first, deduplicated by ts, with `sender`/
    `sender_id` forward-filled (Slack omits the sender element on grouped/
    consecutive messages -- see parser.py) and `thread_ts` set (None for top-level
    messages, the parent's ts for thread replies).
    """
    floor_ts = max(t for t in (last_known_ts, since_ts) if t is not None) if (last_known_ts or since_ts) else None

    collected: dict[str, dict] = {}
    thread_replies: dict[str, list[dict]] = {}
    previous_height = -1

    for scroll_attempt in range(MAX_SCROLLS_PER_CHANNEL):
        for msg in parse_visible_messages(page):
            if floor_ts is not None and msg["ts"] <= floor_ts:
                continue
            if until_ts is not None and msg["ts"] > until_ts:
                continue
            is_new = msg["ts"] not in collected
            if is_new:
                # First sighting wins rather than always overwriting: the
                # DOM can render transient/stale duplicates right after a
                # thread panel closes (see collect_thread_replies), and a
                # later re-scan momentarily catching a corrupted reply_count
                # for an already-known message shouldn't clobber the good
                # reading we already have.
                collected[msg["ts"]] = msg

            if collect_threads and is_new and msg["reply_count"] > 0 and msg["ts"] not in thread_replies:
                replies = collect_thread_replies(
                    page, msg["ts"], seed_sender=msg["sender"], seed_sender_id=msg["sender_id"]
                )
                if replies:
                    thread_replies[msg["ts"]] = replies

        height = _scroll_container_height(page)
        if height == previous_height:
            log.debug("Reached top of channel history after %d scrolls", scroll_attempt)
            break
        previous_height = height

        if floor_ts is not None:
            oldest_ts = min((m["ts"] for m in collected.values()), default=None)
            if oldest_ts is not None and oldest_ts <= floor_ts:
                break

        _scroll_to_top(page)
        page.wait_for_timeout(SCROLL_WAIT_MS)
    else:
        log.warning("Hit MAX_SCROLLS_PER_CHANNEL safety cap; history may be incomplete")

    ordered = sorted(collected.values(), key=lambda m: m["ts"])
    last_sender, last_sender_id = seed_sender, seed_sender_id
    for msg in ordered:
        if msg["sender"] is None:
            msg["sender"] = last_sender or "unknown"
            msg["sender_id"] = last_sender_id
        else:
            last_sender, last_sender_id = msg["sender"], msg["sender_id"]
        msg["thread_ts"] = None

    # Merge, keyed by ts: thread replies win on collision. Slack sometimes
    # also renders a thread's replies inline in the main timeline (observed
    # in 1:1 DMs, which don't hide threaded messages the way channels do),
    # so the same ts can show up both as a "top-level" scroll hit (thread_ts
    # forced None above) and as a properly-tagged reply -- the latter is the
    # correct one.
    final: dict[str, dict] = {msg["ts"]: msg for msg in ordered}
    for replies in thread_replies.values():
        for reply in replies:
            final[reply["ts"]] = reply
    return sorted(final.values(), key=lambda m: m["ts"])
