"""
Launches a Chrome instance dedicated to this tool: a persistent profile
(so you only log into Slack once) with the CDP remote debugging port open
(so `connect_slack_page()` can attach to it).

Deliberately never touches your everyday Chrome -- a distinct
--user-data-dir means this runs as a fully separate process that can
coexist with your normal, already-running Chrome window.

Works on both macOS and Windows: `find_chrome_executable()` checks the
usual install locations for each OS, falling back to whatever `chrome` /
`google-chrome` resolves to on PATH.
"""

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from slack_msg_reader.config import CDP_PORT, CDP_URL, CHROME_PROFILE_DIR

_MACOS_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
]

_WINDOWS_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


class ChromeNotFoundError(RuntimeError):
    pass


def find_chrome_executable() -> str | None:
    if sys.platform == "darwin":
        candidates = _MACOS_CANDIDATES
        which_names = ["google-chrome"]
    elif sys.platform.startswith("win"):
        candidates = _WINDOWS_CANDIDATES
        which_names = ["chrome", "chrome.exe"]
    else:
        candidates = []
        which_names = ["google-chrome", "chromium", "chromium-browser"]

    for path in candidates:
        if os.path.exists(path):
            return path
    for name in which_names:
        found = shutil.which(name)
        if found:
            return found
    return None


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

    chrome_path = find_chrome_executable()
    if not chrome_path:
        raise ChromeNotFoundError(
            "Could not find a Google Chrome install. Please install Chrome and try again."
        )

    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            chrome_path,
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
