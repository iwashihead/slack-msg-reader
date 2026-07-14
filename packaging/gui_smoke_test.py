"""Headless-friendly GUI smoke test: renders the real MainWindow and saves a
screenshot via Qt's own QWidget.grab() -- this works even on CI runners
without OS-level screen-recording permissions, since it doesn't touch the
OS screenshot APIs at all. Used to verify the GUI actually renders on a
given OS/architecture (see .github/workflows/windows-gui-smoke-test.yml)."""

import argparse
import sys

from PySide6.QtWidgets import QApplication

from slack_msg_reader.db.database import init_db
from slack_msg_reader.gui.main_window import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Path to save a PNG screenshot of the rendered window")
    args = parser.parse_args()

    init_db()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.processEvents()

    pixmap = window.grab()
    if pixmap.isNull() or not pixmap.save(args.out):
        print("Failed to render/save screenshot", file=sys.stderr)
        sys.exit(1)

    print(f"Saved screenshot to {args.out} ({pixmap.width()}x{pixmap.height()})")


if __name__ == "__main__":
    main()
