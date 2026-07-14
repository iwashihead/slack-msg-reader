"""
Enumerates the channels/DMs visible in the Slack sidebar for the logged-in user.

Each sidebar row carries its own `data-qa-channel-sidebar-channel-type`
attribute (confirmed values seen in practice: "im" for 1:1 DMs; Slack also
uses "channel"/"private_channel"/"mpdm" for the other kinds), so no section-
heading guessing is needed -- we classify straight off that attribute.
"""

from playwright.sync_api import Page

from slack_msg_reader.scraper.selectors import (
    SIDEBAR_CHANNEL_ID_ATTR,
    SIDEBAR_CHANNEL_ITEM,
    SIDEBAR_CHANNEL_NAME,
    SIDEBAR_CHANNEL_TYPE_ATTR,
)

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


def list_channels(page: Page, max_scroll_attempts: int = 40) -> list[dict]:
    """Scrolls the sidebar to force-render virtualized items, then reads them all.

    Returns a de-duplicated list of {id, name, kind} dicts.
    """
    sidebar = page.locator('[data-qa="slack_kit_list"], nav').first
    previous_count = -1
    for _ in range(max_scroll_attempts):
        raw = page.evaluate(
            _LIST_CHANNELS_JS,
            [SIDEBAR_CHANNEL_ITEM, SIDEBAR_CHANNEL_ID_ATTR, SIDEBAR_CHANNEL_TYPE_ATTR, SIDEBAR_CHANNEL_NAME],
        )
        if len(raw) == previous_count:
            break
        previous_count = len(raw)
        try:
            sidebar.hover()
            page.mouse.wheel(0, 2000)
        except Exception:
            break
        page.wait_for_timeout(300)

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
