"""
Launches a Chrome instance dedicated to this tool: a persistent profile
(so you only log into Slack once) with the CDP remote debugging port open
(so `connect_slack_page()` can attach to it).

Deliberately never touches your everyday Chrome -- a distinct
--user-data-dir means this runs as a fully separate process that can
coexist with your normal, already-running Chrome window.
"""

import os
import subprocess
import time
import urllib.error
import urllib.request

from slack_msg_reader.config import CDP_PORT, CDP_URL, CHROME_APP_PATH, CHROME_PROFILE_DIR


class ChromeNotFoundError(RuntimeError):
    pass


def is_cdp_ready() -> bool:
    try:
        urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=1)
        return True
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False


def launch(open_url: str = "https://app.slack.com/client", timeout_seconds: float = 15.0) -> bool:
    """Starts the dedicated Chrome if it isn't already up. Returns True once CDP responds."""
    if is_cdp_ready():
        return True

    if not os.path.exists(CHROME_APP_PATH):
        raise ChromeNotFoundError(f"Chrome not found at {CHROME_APP_PATH}")

    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            CHROME_APP_PATH,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={CHROME_PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            open_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if is_cdp_ready():
            return True
        time.sleep(0.5)
    return False
