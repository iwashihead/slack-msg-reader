import sys

from PySide6.QtWidgets import QApplication

from slack_msg_reader.db.database import init_db
from slack_msg_reader.gui.main_window import MainWindow


def main() -> None:
    init_db()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
