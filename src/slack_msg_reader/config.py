import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# When frozen (PyInstaller), __file__ resolves inside the app bundle itself,
# which is read-only when run straight from a mounted .dmg and shouldn't be
# written into even once installed (breaks code-signing, needs elevated
# permissions under Program Files on Windows, etc). Use a per-user directory
# instead, matching CHROME_PROFILE_DIR below. Source/CLI runs keep the data
# next to the project as before.
if getattr(sys, "frozen", False):
    DATA_DIR = Path.home() / ".slack-msg-reader" / "data"
else:
    DATA_DIR = PROJECT_ROOT / "data"

DB_PATH = DATA_DIR / "slack_archive.db"
DB_URL = f"sqlite:///{DB_PATH}"

# Chrome must already be running with --remote-debugging-port=<this port>
# and have a tab logged into Slack (see README). `slack chrome` starts such
# a Chrome for you, using a dedicated profile below so it doesn't disturb
# your everyday Chrome window/profile.
CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"

# Persistent (not throwaway) Chrome profile dedicated to this tool. Chrome
# refuses to expose remote debugging on your *default* profile for security
# reasons, so this must be a separate directory -- but it's kept around
# between runs so you only log into Slack here once.
CHROME_PROFILE_DIR = Path.home() / ".slack-msg-reader" / "chrome-profile"

# How long to wait for new message elements to render after each scroll (ms).
SCROLL_WAIT_MS = 600
# Max scroll-up attempts per channel before giving up (safety cap for full history pulls).
MAX_SCROLLS_PER_CHANNEL = 2000
