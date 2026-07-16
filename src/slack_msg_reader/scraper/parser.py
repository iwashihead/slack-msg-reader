"""
Parses currently-rendered Slack message DOM nodes into plain dicts.

Works for both the main channel view and an open thread panel -- Slack
reuses the exact same message markup in both places (confirmed live), so
the only difference is scoping the query to the thread panel's subtree via
`root_selector` (see message_scraper.collect_thread_replies) instead of the
whole document, since both can have message containers on screen at once.

The message's own `data-msg-ts` attribute (present directly on the
MESSAGE_CONTAINER element) gives the exact Slack `ts` value with no
regex/href parsing needed -- confirmed against a live session.

Slack visually groups consecutive messages from the same sender: only the
first message in such a run renders a sender element at all (confirmed
against a live session -- grouped messages carry no sender info anywhere in
their DOM, not even in an aria-hidden helper). `sender`/`sender_id` are
therefore `None` for those; the caller (message_scraper.collect_channel_messages)
is responsible for forward-filling them from the preceding message.

The sender element also carries the real, stable Slack user id (e.g.
"U0123ABC", or "USLACKBOT" for Slackbot -- confirmed present even for bot
senders) in a `data-message-sender` attribute. This is used as `sender_id`
and is what identity should be keyed on, not the display-name text alone,
which can change or collide between people.
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
    MESSAGE_SENDER_ID_ATTR,
    MESSAGE_TEXT,
    MESSAGE_THREAD_REPLY_BAR,
    MESSAGE_TS_ATTR,
)

_DIGITS_RE = re.compile(r"(\d+)")

_PARSE_JS = """
([containerSel, tsAttr, senderSel, senderIdAttr, textSel, replyBarSel, reactionSel, reactionEmojiImgSel, reactionEmojiAttr, reactionCountSel, rootSel]) => {
    const root = rootSel ? document.querySelector(rootSel) : document;
    const nodes = root ? Array.from(root.querySelectorAll(containerSel)) : [];
    return nodes.map((el) => {
        const senderEl = el.querySelector(senderSel);
        const textEl = el.querySelector(textSel);
        const replyBarEl = el.querySelector(replyBarSel);
        const reactionEls = Array.from(el.querySelectorAll(reactionSel));
        const reactions = reactionEls.map((r) => {
            const emojiImg = r.querySelector(reactionEmojiImgSel);
            const countEl = r.querySelector(reactionCountSel);
            return {
                // Prefer the stringify attribute, but not every emoji variant
                // carries it (confirmed live: some reactions crash the whole
                // collect run when two different-but-unidentifiable emoji on
                // the same message both fell back to a shared placeholder) --
                // `alt` carries the same ":shortcode:" text in the normal case
                // and is a second independent chance to get a real identifier.
                emoji: emojiImg ? (emojiImg.getAttribute(reactionEmojiAttr) || emojiImg.getAttribute('alt')) : null,
                count_text: countEl ? countEl.textContent : '',
            };
        });
        return {
            ts: el.getAttribute(tsAttr),
            sender: senderEl ? senderEl.textContent.trim() : null,
            sender_id: senderEl ? senderEl.getAttribute(senderIdAttr) : null,
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
    """Returns (emoji, count) pairs, deduplicated by emoji name.

    Merging (summing counts) rather than keeping duplicates as separate
    entries matters because `reactions` has a UNIQUE(message_id, emoji)
    constraint: if two genuinely different emoji both fail to yield an
    identifiable name (confirmed live -- some emoji variants carry neither
    of the two attributes checked in the JS above) they'd otherwise collide
    as two "unknown" rows for the same message and crash the insert.
    """
    counts: dict[str, int] = {}
    for r in raw_reactions:
        count_m = _DIGITS_RE.search(r.get("count_text") or "")
        count = int(count_m.group(1)) if count_m else 0
        emoji = (r.get("emoji") or "unknown").strip(":") or "unknown"
        counts[emoji] = counts.get(emoji, 0) + count
    return list(counts.items())


def parse_visible_messages(page: Page, root_selector: str | None = None) -> list[dict]:
    """Returns parsed dicts for every message container currently in the DOM.

    Fields: sender (display name str | None), sender_id (real Slack user id
    str | None) -- both None means "same as the previous message", see
    module docstring), ts, text, reply_count, reactions (list[(emoji, count)]).

    `root_selector`, when given, scopes the search to that subtree (e.g. the
    thread flexpane) instead of the whole document -- needed because a
    thread panel and the main channel view can have their own
    MESSAGE_CONTAINER elements on screen at the same time.
    """
    raw = page.evaluate(
        _PARSE_JS,
        [
            MESSAGE_CONTAINER,
            MESSAGE_TS_ATTR,
            MESSAGE_SENDER,
            MESSAGE_SENDER_ID_ATTR,
            MESSAGE_TEXT,
            MESSAGE_THREAD_REPLY_BAR,
            MESSAGE_REACTION,
            MESSAGE_REACTION_EMOJI_IMG,
            MESSAGE_REACTION_EMOJI_ATTR,
            MESSAGE_REACTION_COUNT,
            root_selector,
        ],
    )
    parsed = []
    for item in raw:
        ts = item.get("ts")
        if not ts:
            continue  # can't dedupe/store without a stable ts, skip
        parsed.append(
            {
                "sender": item.get("sender") or None,
                "sender_id": item.get("sender_id") or None,
                "ts": ts,
                "text": item.get("text") or "",
                "reply_count": _extract_reply_count(item.get("reply_bar_text")),
                "reactions": _extract_reactions(item.get("reactions") or []),
            }
        )
    return parsed
