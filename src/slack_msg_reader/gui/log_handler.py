"""Bridges the standard `logging` module into a Qt signal so log lines from
collect.py / message_scraper.py etc. can be shown live in a QTextEdit."""

import logging

from PySide6.QtCore import QObject, Signal


class QtLogHandler(logging.Handler, QObject):
    line_logged = Signal(str)

    def __init__(self) -> None:
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        self.line_logged.emit(self.format(record))
