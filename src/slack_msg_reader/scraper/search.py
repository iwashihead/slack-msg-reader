"""
Search-based collection: for a given real Slack user id, uses Slack's own
search (`from:<@USERID>`, sorted newest-first by default) to find that
person's messages across the whole workspace directly, rather than
scrolling every channel's full history looking for them.

This is lower-fidelity than the regular per-channel scraper in
message_scraper.py -- no reactions, no thread-reply awareness, and search
result text may not reflect later edits the same way -- but it's much
faster when the only messages of interest are one person's, since Slack's
own index (not our scroll loop) does the filtering.

Confirmed live, the hard way: once (during development, after a lot of
rapid repeated searches) a stale/stuck autocomplete overlay left every
`.click()` on the search input hanging indefinitely -- surviving even a
full Chrome restart, since Slack persists the search draft client-side.
`.focus()` sidesteps this, since it doesn't go through Playwright's
pointer-interception actionability check the way `.click()` does, so the
input is focused that way; the search *button* itself is opened with a
plain `.click()` (a keyboard shortcut was tried too, but synthetic CDP key
events didn't reliably trigger Slack's own shortcut handler -- clicking
the button was the more consistent option in practice). Submitting needs
an explicit ArrowDown then Enter -- a plain Enter alone left the typed
query sitting as an unsubmitted autocomplete suggestion rather than
actually searching.
"""

import logging

from playwright.sync_api import Page

log = logging.getLogger(__name__)

_SEARCH_BUTTON = '[data-qa="top_nav_search"]'
_SEARCH_INPUT = '[data-qa="texty_input"][role="combobox"]'
_SEARCH_RESULT_ITEM = '[data-qa="search_result"]'
_SEARCH_RESULT_SENDER = '[data-qa="message_sender_name"]'
_SEARCH_RESULT_SENDER_ID_ATTR = "data-message-sender"
_SEARCH_RESULT_CHANNEL = '[data-qa="inline_channel_entity"]'
_SEARCH_RESULT_CHANNEL_ID_ATTR = "data-channel-id"
_SEARCH_RESULT_CHANNEL_NAME = '[data-qa="inline_channel_entity__name"]'
_SEARCH_RESULT_TS_LINK = "a.c-timestamp"
_SEARCH_RESULT_TEXT = '[data-qa="message-text"]'


def _select_all_shortcut() -> str:
    import sys

    return "Meta+A" if sys.platform == "darwin" else "Control+A"


def _open_search(page: Page, timeout: int = 10000) -> bool:
    btn = page.query_selector(_SEARCH_BUTTON)
    if btn is None:
        return False
    try:
        btn.click(timeout=timeout)
        page.wait_for_selector(_SEARCH_INPUT, timeout=timeout)
    except Exception:
        log.warning("Clicking the search button didn't surface the search input", exc_info=True)
        return False
    return True


def _submit_query(page: Page, query: str) -> bool:
    """Types query into the search box and submits it. Returns True if the
    page navigated to the search results view."""
    inp = page.query_selector(_SEARCH_INPUT)
    if inp is None:
        return False

    inp.focus()
    page.wait_for_timeout(200)
    page.keyboard.press(_select_all_shortcut())
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    page.keyboard.type(query, delay=20)
    page.wait_for_timeout(900)
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    page.keyboard.press("Enter")
    page.wait_for_timeout(2000)
    return "/search" in page.url


def _parse_result_item(item) -> dict | None:
    sender_el = item.query_selector(_SEARCH_RESULT_SENDER)
    channel_el = item.query_selector(_SEARCH_RESULT_CHANNEL)
    channel_name_el = item.query_selector(_SEARCH_RESULT_CHANNEL_NAME)
    ts_link = item.query_selector(_SEARCH_RESULT_TS_LINK)
    text_el = item.query_selector(_SEARCH_RESULT_TEXT)

    ts = ts_link.get_attribute("data-ts") if ts_link else None
    channel_id = channel_el.get_attribute(_SEARCH_RESULT_CHANNEL_ID_ATTR) if channel_el else None
    if not ts or not channel_id:
        return None

    return {
        "ts": ts,
        "channel_id": channel_id,
        "channel_name": channel_name_el.inner_text().strip() if channel_name_el else channel_id,
        "sender": sender_el.inner_text().strip() if sender_el else "unknown",
        "sender_id": sender_el.get_attribute(_SEARCH_RESULT_SENDER_ID_ATTR) if sender_el else None,
        "text": text_el.inner_text().strip() if text_el else "",
    }


def search_messages_from_user(page: Page, user_id: str, max_pages: int = 25) -> list[dict]:
    """Returns that user's messages across the whole workspace, newest-first
    (matching Slack's own default search sort), by driving `from:<@user_id>`
    search instead of scrolling channels.

    Each dict: ts, channel_id, channel_name, sender, sender_id, text.
    Returns [] if search couldn't be opened/submitted (caller should treat
    this as "give up", not "zero messages exist").
    """
    if not _open_search(page):
        log.warning("Could not open Slack search (clicking the search button didn't surface the search box)")
        return []

    if not _submit_query(page, f"from:<@{user_id}>"):
        log.warning("Search submission for user id=%s did not reach the results view", user_id)
        return []

    results: dict[str, dict] = {}
    page_num = 1
    while page_num <= max_pages:
        for item in page.query_selector_all(_SEARCH_RESULT_ITEM):
            parsed = _parse_result_item(item)
            if parsed:
                results[parsed["ts"]] = parsed

        next_btn = page.query_selector(f'[data-qa="c-pagination_page_btn_{page_num + 1}"]')
        if not next_btn:
            break
        next_btn.click(timeout=5000)
        page.wait_for_timeout(1200)
        page_num += 1
    else:
        log.warning("Hit max_pages (%d) while paging through search results; some may be missing", max_pages)

    return sorted(results.values(), key=lambda m: m["ts"], reverse=True)
