"""
CSS/DOM selectors for the Slack web client.

IMPORTANT: Slack does not publish or guarantee this markup. These values are
best-effort, based on the `data-qa` attributes Slack's own frontend has used
historically (data-qa attributes are for their internal QA tooling and tend
to be more stable than generated class names, but they still change between
Slack releases with no notice or changelog).

Before your first real run, use `python -m slack_msg_reader.collect inspect`
(see README) to confirm each selector below still matches something in your
actual Slack tab, and update this file if it doesn't.
"""

# --- Sidebar (channel list) ---
SIDEBAR_CHANNEL_ITEM = 'div[data-qa="virtual-list-item"] a[data-qa-channel-sidebar-channel-id]'
SIDEBAR_CHANNEL_ID_ATTR = "data-qa-channel-sidebar-channel-id"
SIDEBAR_CHANNEL_NAME = '.p-channel_sidebar__name'
SIDEBAR_SECTION_HEADER = '[data-qa="channel-section-heading"]'

# --- Message pane ---
MESSAGE_LIST_SCROLL_CONTAINER = '[data-qa="slack_kit_scrollbar"]'
MESSAGE_CONTAINER = '[data-qa="virtual-list-item"] [data-qa="message_container"]'
MESSAGE_SENDER = '[data-qa="message_sender"]'
MESSAGE_TIMESTAMP_LINK = 'a[data-qa="message_timestamp"]'
MESSAGE_TEXT = '[data-qa="message-text"]'
MESSAGE_REACTION = 'button[data-qa="reaction"]'
MESSAGE_REACTION_COUNT = '.c-reaction__count'
MESSAGE_REACTION_EMOJI_LABEL_ATTR = "aria-label"
MESSAGE_THREAD_REPLY_BAR = '[data-qa="reply_bar"]'
