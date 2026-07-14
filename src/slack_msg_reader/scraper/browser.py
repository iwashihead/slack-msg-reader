"""
Attaches to an already-running Chrome instance over the Chrome DevTools Protocol
(CDP) and finds an existing, already-logged-in Slack tab.

This deliberately never performs a Slack login itself: the human logs into
Slack manually in their normal browser first (see README for the
--remote-debugging-port setup), and this module just reuses that session.
"""

from contextlib import contextmanager

from playwright.sync_api import Page, sync_playwright

from slack_msg_reader.config import CDP_URL


class SlackTabNotFoundError(RuntimeError):
    pass


def _find_slack_page(browser) -> Page:
    for context in browser.contexts:
        for page in context.pages:
            if "app.slack.com/client" in page.url:
                return page
    raise SlackTabNotFoundError(
        "No open app.slack.com tab found on the attached browser. "
        "Open https://app.slack.com in that Chrome window and log in first."
    )


@contextmanager
def connect_slack_page():
    """Yields the Playwright Page for the already-open, already-authenticated Slack tab."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(CDP_URL)
        try:
            page = _find_slack_page(browser)
            yield page
        finally:
            # Do not close the user's real browser; just detach.
            browser.close()
