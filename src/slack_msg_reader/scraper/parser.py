"""
Parses currently-rendered Slack message DOM nodes into plain dicts.

Only top-level channel messages are parsed (not full thread contents) — for
a message that started a thread we capture its reply_count but not the
individual replies. Expanding threads is a natural follow-up, not needed for
the MVP archive.

The message's own `data-msg-ts` attribute (present directly on the
MESSAGE_CONTAINER element) gives the exact Slack `ts` value with no
regex/href parsing needed -- confirmed against a live session.
"""

import re

from playwright.sync_api import Page

from slack_msg_reader.scraper.selectors import (
    MESSAGE_CONTAINER,
    MESSAGE_REACTION,
    MESSAGE_REACTION_COUNT,
    MESSAGE_REACTION_EMOJI_ATTR,
    MESSAGE_REACTION_EMOJI_IMG,
    MESSAGE_SENDER,
    MESSAGE_TEXT,
    MESSAGE_THREAD_REPLY_BAR,
    MESSAGE_TS_ATTR,
)

_DIGITS_RE = re.compile(r"(\d+)")

_PARSE_JS = """
([containerSel, tsAttr, senderSel, textSel, replyBarSel, reactionSel, reactionEmojiImgSel, reactionEmojiAttr, reactionCountSel]) => {
    const nodes = Array.from(document.querySelectorAll(containerSel));
    return nodes.map((el) => {
        const senderEl = el.querySelector(senderSel);
        const textEl = el.querySelector(textSel);
        const replyBarEl = el.querySelector(replyBarSel);
        const reactionEls = Array.from(el.querySelectorAll(reactionSel));
        const reactions = reactionEls.map((r) => {
            const emojiImg = r.querySelector(reactionEmojiImgSel);
            const countEl = r.querySelector(reactionCountSel);
            return {
                emoji: emojiImg ? emojiImg.getAttribute(reactionEmojiAttr) : null,
                count_text: countEl ? countEl.textContent : '',
            };
        });
        return {
            ts: el.getAttribute(tsAttr),
            sender: senderEl ? senderEl.textContent.trim() : null,
            text: textEl ? textEl.textContent.trim() : '',
            reply_bar_text: replyBarEl ? replyBarEl.textContent.trim() : null,
            reactions,
        };
    });
}
"""


def _extract_reply_count(reply_bar_text: str | None) -> int:
    if not reply_bar_text:
        return 0
    m = _DIGITS_RE.search(reply_bar_text)
    return int(m.group(1)) if m else 0


def _extract_reactions(raw_reactions: list[dict]) -> list[tuple[str, int]]:
    out = []
    for r in raw_reactions:
        count_m = _DIGITS_RE.search(r.get("count_text") or "")
        count = int(count_m.group(1)) if count_m else 0
        emoji = (r.get("emoji") or "unknown").strip(":") or "unknown"
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
            MESSAGE_TS_ATTR,
            MESSAGE_SENDER,
            MESSAGE_TEXT,
            MESSAGE_THREAD_REPLY_BAR,
            MESSAGE_REACTION,
            MESSAGE_REACTION_EMOJI_IMG,
            MESSAGE_REACTION_EMOJI_ATTR,
            MESSAGE_REACTION_COUNT,
        ],
    )
    parsed = []
    for item in raw:
        ts = item.get("ts")
        if not ts:
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
