"""
Enumerates the channels/DMs visible in the Slack sidebar for the logged-in user.

Each sidebar row carries its own `data-qa-channel-sidebar-channel-type`
attribute (confirmed values seen in practice: "im" for 1:1 DMs; Slack also
uses "channel"/"private_channel"/"mpdm" for the other kinds), so no section-
heading guessing is needed -- we classify straight off that attribute.
"""

import logging

from playwright.sync_api import Page

from slack_msg_reader.scraper.selectors import (
    SIDEBAR_CHANNEL_ID_ATTR,
    SIDEBAR_CHANNEL_ITEM,
    SIDEBAR_CHANNEL_NAME,
    SIDEBAR_CHANNEL_TYPE_ATTR,
    SIDEBAR_SCROLL_CONTAINER,
)

log = logging.getLogger(__name__)

_LIST_CHANNELS_JS = """
([itemSel, idAttr, typeAttr, nameSel]) => {
    const items = Array.from(document.querySelectorAll(itemSel));
    return items.map((el) => {
        const nameEl = el.querySelector(nameSel);
        return {
            id: el.getAttribute(idAttr),
            name: (nameEl ? nameEl.textContent : el.textContent).trim(),
            raw_type: el.getAttribute(typeAttr),
        };
    });
}
"""


def _classify(raw_type: str | None) -> str:
    if raw_type in ("im", "mpdm", "mpim"):
        return "dm"
    return "channel"


def _scroll_state(page: Page) -> tuple[int, int, int] | None:
    """Returns (scrollTop, clientHeight, scrollHeight) for the sidebar's own
    scroll container, or None if it isn't found (e.g. very short channel list
    that never renders a scrollable container)."""
    return page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            return [el.scrollTop, el.clientHeight, el.scrollHeight];
        }""",
        SIDEBAR_SCROLL_CONTAINER,
    )


def _scroll_to_bottom(page: Page) -> None:
    page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (el) el.scrollTop = el.scrollHeight;
        }""",
        SIDEBAR_SCROLL_CONTAINER,
    )


def list_channels(page: Page, max_scroll_attempts: int = 500, stable_rounds_required: int = 3) -> list[dict]:
    """Scrolls the sidebar to force-render virtualized items, then reads them all.

    Slack virtualizes the sidebar the same way it virtualizes the message
    list (only rows near the viewport exist in the DOM), so a workspace with
    hundreds of channels needs many scroll passes to fully enumerate -- a
    single scroll tick that happens not to grow the count is not reliable
    proof of having reached the bottom (render can lag a beat behind the
    scroll), so this requires several consecutive stable reads *and*
    confirmation the container's own scrollTop has reached its scrollHeight
    before stopping.

    Returns a de-duplicated list of {id, name, kind} dicts.
    """
    previous_count = -1
    stable_rounds = 0

    for attempt in range(max_scroll_attempts):
        raw = page.evaluate(
            _LIST_CHANNELS_JS,
            [SIDEBAR_CHANNEL_ITEM, SIDEBAR_CHANNEL_ID_ATTR, SIDEBAR_CHANNEL_TYPE_ATTR, SIDEBAR_CHANNEL_NAME],
        )
        count = len(raw)
        stable_rounds = stable_rounds + 1 if count == previous_count else 0
        previous_count = count

        state = _scroll_state(page)
        at_bottom = state is None or (state[0] + state[1] >= state[2] - 2)

        if stable_rounds >= stable_rounds_required and at_bottom:
            log.debug("Sidebar enumeration settled after %d scroll attempts (%d items)", attempt, count)
            break

        _scroll_to_bottom(page)
        page.wait_for_timeout(250)
    else:
        log.warning(
            "Hit max_scroll_attempts (%d) while enumerating the sidebar; channel list may be incomplete",
            max_scroll_attempts,
        )

    raw = page.evaluate(
        _LIST_CHANNELS_JS,
        [SIDEBAR_CHANNEL_ITEM, SIDEBAR_CHANNEL_ID_ATTR, SIDEBAR_CHANNEL_TYPE_ATTR, SIDEBAR_CHANNEL_NAME],
    )

    seen: dict[str, dict] = {}
    for entry in raw:
        cid = entry.get("id")
        if not cid:
            continue
        seen[cid] = {"id": cid, "name": entry["name"], "kind": _classify(entry.get("raw_type"))}
    return list(seen.values())
