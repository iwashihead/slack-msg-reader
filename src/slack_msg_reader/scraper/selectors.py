"""
CSS/DOM selectors for the Slack web client.

Confirmed against a live Slack session (2026-07-14, Chrome 150 / Slack web
client) by round-tripping real sidebar items and a self-sent test message.
Slack does not publish or guarantee this markup and can change it without
notice on any future release -- if `collect inspect` stops finding
channels/messages, re-run the same kind of DOM inspection and update this
file.
"""

# --- Sidebar (channel list) ---
SIDEBAR_CHANNEL_ITEM = '[data-qa="channel-sidebar-channel"]'
SIDEBAR_CHANNEL_ID_ATTR = "data-qa-channel-sidebar-channel-id"
SIDEBAR_CHANNEL_TYPE_ATTR = "data-qa-channel-sidebar-channel-type"  # e.g. "im", "channel", "private_channel", "mpdm"
SIDEBAR_CHANNEL_NAME = ".p-channel_sidebar__name"
# Same virtualized-list pattern as the message pane, confirmed via the same
# live-DOM approach: div[data-qa="slack_kit_list"] wraps the sidebar's rows.
SIDEBAR_SCROLL_CONTAINER = '[data-qa="slack_kit_list"]'

# --- Message pane ---
MESSAGE_LIST_SCROLL_CONTAINER = '[data-qa="slack_kit_scrollbar"]'
MESSAGE_CONTAINER = '[data-qa="virtual-list-item"] [data-qa="message_container"]'
MESSAGE_TS_ATTR = "data-msg-ts"  # present directly on MESSAGE_CONTAINER
MESSAGE_SENDER = '[data-qa="message_sender_name"]'
MESSAGE_TEXT = '[data-qa="message-text"]'
MESSAGE_REACTION = 'button[data-qa="reactji"]'
MESSAGE_REACTION_EMOJI_IMG = 'img[data-qa="emoji"]'
MESSAGE_REACTION_EMOJI_ATTR = "data-stringify-emoji"  # e.g. ":innocent:"
MESSAGE_REACTION_COUNT = ".c-reaction__count"
MESSAGE_THREAD_REPLY_BAR = '[data-qa="reply_bar_count"]'  # e.g. "1 件の返信" -- also the clickable button that opens the thread

# --- Thread panel ---
# Confirmed live: clicking MESSAGE_THREAD_REPLY_BAR opens this flexpane, which
# reuses the exact same message-list markup as the main channel (same
# MESSAGE_CONTAINER/MESSAGE_LIST_SCROLL_CONTAINER selectors, just scoped
# under THREAD_PANEL instead of the whole document) -- including a duplicate
# of the parent message at the top, which the reply-scraping code filters
# out by matching its ts against the already-known parent ts.
THREAD_PANEL = '[data-qa="threads_flexpane"]'
THREAD_CLOSE_BUTTON = '[data-qa="close_flexpane"]'
