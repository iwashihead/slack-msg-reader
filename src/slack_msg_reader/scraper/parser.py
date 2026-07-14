"""
Parses currently-rendered Slack message DOM nodes into plain dicts.

Only top-level channel messages are parsed (not full thread contents) — for
a message that started a thread we capture its reply_count but not the
individual replies. Expanding threads is a natural follow-up, not needed for
the MVP archive.

The Slack message permalink pattern (`/p<10-digit><6-digit>` in the
timestamp link's href) is used to recover the exact `ts` value, since it is
far more stable across Slack frontend releases than any single data-qa
attribute.
"""

import re

from playwright.sync_api import Page

from slack_msg_reader.scraper.selectors import (
    MESSAGE_CONTAINER,
    MESSAGE_REACTION,
    MESSAGE_REACTION_COUNT,
    MESSAGE_SENDER,
    MESSAGE_TEXT,
    MESSAGE_THREAD_REPLY_BAR,
    MESSAGE_TIMESTAMP_LINK,
)

_PERMALINK_TS_RE = re.compile(r"/p(\d{10})(\d{6})(?:\D|$)")
_REPLY_COUNT_RE = re.compile(r"(\d+)")

_PARSE_JS = """
([containerSel, senderSel, tsLinkSel, textSel, replyBarSel, reactionSel, reactionCountSel]) => {
    const nodes = Array.from(document.querySelectorAll(containerSel));
    return nodes.map((el) => {
        const senderEl = el.querySelector(senderSel);
        const tsEl = el.querySelector(tsLinkSel);
        const textEl = el.querySelector(textSel);
        const replyBarEl = el.querySelector(replyBarSel);
        const reactionEls = Array.from(el.querySelectorAll(reactionSel));
        const reactions = reactionEls.map((r) => {
            const countEl = r.querySelector(reactionCountSel);
            return {
                aria_label: r.getAttribute('aria-label') || '',
                count_text: countEl ? countEl.textContent : '',
            };
        });
        return {
            sender: senderEl ? senderEl.textContent.trim() : null,
            ts_href: tsEl ? tsEl.getAttribute('href') : null,
            text: textEl ? textEl.textContent.trim() : '',
            reply_bar_text: replyBarEl ? replyBarEl.textContent.trim() : null,
            reactions,
        };
    });
}
"""


def _extract_ts(href: str | None) -> str | None:
    if not href:
        return None
    m = _PERMALINK_TS_RE.search(href)
    if not m:
        return None
    return f"{m.group(1)}.{m.group(2)}"


def _extract_reply_count(reply_bar_text: str | None) -> int:
    if not reply_bar_text:
        return 0
    m = _REPLY_COUNT_RE.search(reply_bar_text)
    return int(m.group(1)) if m else 0


def _extract_reactions(raw_reactions: list[dict]) -> list[tuple[str, int]]:
    out = []
    for r in raw_reactions:
        count_m = _REPLY_COUNT_RE.search(r.get("count_text") or "")
        count = int(count_m.group(1)) if count_m else 0
        label = (r.get("aria_label") or "").strip()
        emoji = label.split(",")[0].split(" reaction")[0].strip() or "unknown"
        out.append((emoji, count))
    return out


def parse_visible_messages(page: Page) -> list[dict]:
    """Returns parsed dicts for every message container currently in the DOM.

    Fields: sender (display name str), ts (str | None), text, reply_count,
    reactions (list[(emoji, count)]).
    """
    raw = page.evaluate(
        _PARSE_JS,
        [
            MESSAGE_CONTAINER,
            MESSAGE_SENDER,
            MESSAGE_TIMESTAMP_LINK,
            MESSAGE_TEXT,
            MESSAGE_THREAD_REPLY_BAR,
            MESSAGE_REACTION,
            MESSAGE_REACTION_COUNT,
        ],
    )
    parsed = []
    for item in raw:
        ts = _extract_ts(item.get("ts_href"))
        if ts is None:
            continue  # can't dedupe/store without a stable ts, skip
        parsed.append(
            {
                "sender": item.get("sender") or "unknown",
                "ts": ts,
                "text": item.get("text") or "",
                "reply_count": _extract_reply_count(item.get("reply_bar_text")),
                "reactions": _extract_reactions(item.get("reactions") or []),
            }
        )
    return parsed
