"""
Enumerates the channels/DMs visible in the Slack sidebar for the logged-in user.

Slack no longer reliably distinguishes public vs. private channels by ID
prefix, and the sidebar's own icon markup for that distinction is not stable
enough to key logic off. For this tool the meaningful split is only
"channel" (public or private, scraped identically) vs "dm" (DM or group DM),
read from the section heading text ("Channels" vs "Direct messages").
"""

from playwright.sync_api import Page

from slack_msg_reader.scraper.selectors import (
    SIDEBAR_CHANNEL_ID_ATTR,
    SIDEBAR_CHANNEL_ITEM,
    SIDEBAR_CHANNEL_NAME,
    SIDEBAR_SECTION_HEADER,
)

_LIST_CHANNELS_JS = """
([itemSel, idAttr, nameSel, headerSel]) => {
    const items = Array.from(document.querySelectorAll(itemSel));
    const headers = Array.from(document.querySelectorAll(headerSel));

    function sectionFor(el) {
        let best = null;
        for (const h of headers) {
            if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) {
                best = h;
            }
        }
        return best ? best.textContent.trim() : '';
    }

    return items.map((a) => {
        const nameEl = a.querySelector(nameSel);
        return {
            id: a.getAttribute(idAttr),
            name: (nameEl ? nameEl.textContent : a.textContent).trim(),
            section: sectionFor(a),
        };
    });
}
"""


def _classify(section_text: str) -> str:
    lowered = section_text.lower()
    if "direct" in lowered or "dm" in lowered:
        return "dm"
    return "channel"


def list_channels(page: Page, max_scroll_attempts: int = 40) -> list[dict]:
    """Scrolls the sidebar to force-render virtualized items, then reads them all.

    Returns a de-duplicated list of {id, name, kind} dicts.
    """
    sidebar = page.locator('[data-qa="workspace-nav"], nav').first
    previous_count = -1
    for _ in range(max_scroll_attempts):
        raw = page.evaluate(
            _LIST_CHANNELS_JS,
            [SIDEBAR_CHANNEL_ITEM, SIDEBAR_CHANNEL_ID_ATTR, SIDEBAR_CHANNEL_NAME, SIDEBAR_SECTION_HEADER],
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
        [SIDEBAR_CHANNEL_ITEM, SIDEBAR_CHANNEL_ID_ATTR, SIDEBAR_CHANNEL_NAME, SIDEBAR_SECTION_HEADER],
    )

    seen: dict[str, dict] = {}
    for entry in raw:
        cid = entry.get("id")
        if not cid:
            continue
        seen[cid] = {"id": cid, "name": entry["name"], "kind": _classify(entry["section"])}
    return list(seen.values())
