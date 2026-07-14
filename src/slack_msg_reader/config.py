from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "slack_archive.db"
DB_URL = f"sqlite:///{DB_PATH}"

# Chrome must already be running with --remote-debugging-port=<this port>
# and have a tab logged into Slack (see README).
CDP_URL = "http://localhost:9222"

# How long to wait for new message elements to render after each scroll (ms).
SCROLL_WAIT_MS = 600
# Max scroll-up attempts per channel before giving up (safety cap for full history pulls).
MAX_SCROLLS_PER_CHANNEL = 2000
