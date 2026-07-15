import logging
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slack_msg_reader.gui.log_handler import QtLogHandler
from slack_msg_reader.gui.workers import ChromeWorker, CollectWorker, InspectWorker

_CHECK_COL, _KIND_COL, _ID_COL, _NAME_COL = range(4)


class ChromeCollectTab(QWidget):
    def __init__(self):
        super().__init__()

        self._log_handler = QtLogHandler()
        self._log_handler.line_logged.connect(self._append_log)
        logging.getLogger().addHandler(self._log_handler)
        logging.getLogger().setLevel(logging.INFO)

        self._chrome_worker: ChromeWorker | None = None
        self._inspect_worker: InspectWorker | None = None
        self._collect_worker: CollectWorker | None = None

        layout = QVBoxLayout(self)

        chrome_box = QGroupBox("1. Chrome")
        chrome_layout = QHBoxLayout(chrome_box)
        self.chrome_button = QPushButton("Start Chrome")
        self.chrome_button.clicked.connect(self._start_chrome)
        self.chrome_status = QLabel("Not checked yet.")
        chrome_layout.addWidget(self.chrome_button)
        chrome_layout.addWidget(self.chrome_status, 1)
        layout.addWidget(chrome_box)

        inspect_box = QGroupBox("2. Inspect (channel list) -- check specific channels to limit Collect to them")
        inspect_layout = QVBoxLayout(inspect_box)
        inspect_buttons = QHBoxLayout()
        self.inspect_button = QPushButton("Inspect")
        self.inspect_button.clicked.connect(self._start_inspect)
        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_button = QPushButton("Select none")
        self.select_none_button.clicked.connect(lambda: self._set_all_checked(False))
        inspect_buttons.addWidget(self.inspect_button)
        inspect_buttons.addWidget(self.select_all_button)
        inspect_buttons.addWidget(self.select_none_button)
        inspect_layout.addLayout(inspect_buttons)
        self.channel_table = QTableWidget(0, 4)
        self.channel_table.setHorizontalHeaderLabels(["", "kind", "id", "name"])
        self.channel_table.horizontalHeader().setStretchLastSection(True)
        self.channel_table.setColumnWidth(_CHECK_COL, 24)
        inspect_layout.addWidget(self.channel_table)
        layout.addWidget(inspect_box)

        collect_box = QGroupBox("3. Collect")
        collect_form = QFormLayout()
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(["all", "channel", "dm"])
        collect_form.addRow("Kind (used only if no channels checked above):", self.kind_combo)
        self.name_contains_edit = QLineEdit()
        self.name_contains_edit.setPlaceholderText("(optional) filter by channel name substring")
        collect_form.addRow("Name contains:", self.name_contains_edit)
        self.full_history_checkbox = QCheckBox("Re-walk full history (ignore what's already stored)")
        collect_form.addRow(self.full_history_checkbox)
        self.threads_checkbox = QCheckBox("Also collect thread replies (slower)")
        self.threads_checkbox.setChecked(True)
        collect_form.addRow(self.threads_checkbox)

        since_row = QHBoxLayout()
        self.since_checkbox = QCheckBox("Since:")
        self.since_edit = QDateEdit(calendarPopup=True)
        self.since_edit.setDate(datetime.now().date().replace(day=1))
        self.since_edit.setEnabled(False)
        self.since_checkbox.toggled.connect(self.since_edit.setEnabled)
        since_row.addWidget(self.since_checkbox)
        since_row.addWidget(self.since_edit)
        collect_form.addRow(since_row)

        until_row = QHBoxLayout()
        self.until_checkbox = QCheckBox("Until:")
        self.until_edit = QDateEdit(calendarPopup=True)
        self.until_edit.setDate(datetime.now().date())
        self.until_edit.setEnabled(False)
        self.until_checkbox.toggled.connect(self.until_edit.setEnabled)
        until_row.addWidget(self.until_checkbox)
        until_row.addWidget(self.until_edit)
        collect_form.addRow(until_row)

        self.collect_button = QPushButton("Collect")
        self.collect_button.clicked.connect(self._start_collect)
        collect_form.addRow(self.collect_button)
        collect_vbox = QVBoxLayout(collect_box)
        collect_vbox.addLayout(collect_form)
        layout.addWidget(collect_box)

        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        layout.addWidget(log_box, 1)

    def _append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def _set_busy(self, busy: bool) -> None:
        for btn in (self.chrome_button, self.inspect_button, self.collect_button):
            btn.setEnabled(not busy)

    # --- Chrome ---
    def _start_chrome(self) -> None:
        self._set_busy(True)
        self.chrome_status.setText("Starting Chrome...")
        self._chrome_worker = ChromeWorker()
        self._chrome_worker.finished_ok.connect(self._on_chrome_finished)
        self._chrome_worker.failed.connect(self._on_chrome_failed)
        self._chrome_worker.finished.connect(lambda: self._set_busy(False))
        self._chrome_worker.start()

    def _on_chrome_finished(self, ready: bool) -> None:
        if ready:
            self.chrome_status.setText(
                "Chrome is ready. First time? Log into Slack manually in the window that opened."
            )
        else:
            self.chrome_status.setText("Chrome started but the debug port never came up. Try again.")

    def _on_chrome_failed(self, message: str) -> None:
        self.chrome_status.setText(f"Error: {message}")

    # --- Inspect ---
    def _start_inspect(self) -> None:
        self._set_busy(True)
        self.channel_table.setRowCount(0)
        self._inspect_worker = InspectWorker()
        self._inspect_worker.finished_ok.connect(self._on_inspect_finished)
        self._inspect_worker.failed.connect(self._on_inspect_failed)
        self._inspect_worker.finished.connect(lambda: self._set_busy(False))
        self._inspect_worker.start()

    def _on_inspect_finished(self, url: str, channels: list) -> None:
        self._append_log(f"Attached to: {url}")
        self._append_log(f"Sidebar channels found: {len(channels)}")
        self.channel_table.setRowCount(len(channels))
        for row, ch in enumerate(channels):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check_item.setCheckState(Qt.CheckState.Unchecked)
            self.channel_table.setItem(row, _CHECK_COL, check_item)
            self.channel_table.setItem(row, _KIND_COL, QTableWidgetItem(ch["kind"]))
            self.channel_table.setItem(row, _ID_COL, QTableWidgetItem(ch["id"]))
            self.channel_table.setItem(row, _NAME_COL, QTableWidgetItem(ch["name"]))

    def _on_inspect_failed(self, message: str) -> None:
        self._append_log(f"Inspect failed: {message}")

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.channel_table.rowCount()):
            item = self.channel_table.item(row, _CHECK_COL)
            if item:
                item.setCheckState(state)

    def _checked_channel_ids(self) -> list[str]:
        ids = []
        for row in range(self.channel_table.rowCount()):
            check_item = self.channel_table.item(row, _CHECK_COL)
            if check_item and check_item.checkState() == Qt.CheckState.Checked:
                id_item = self.channel_table.item(row, _ID_COL)
                if id_item:
                    ids.append(id_item.text())
        return ids

    # --- Collect ---
    def _start_collect(self) -> None:
        self._set_busy(True)

        since = None
        if self.since_checkbox.isChecked():
            d = self.since_edit.date().toPython()
            since = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)

        until = None
        if self.until_checkbox.isChecked():
            d = self.until_edit.date().toPython()
            until = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1, microseconds=-1)

        channel_ids = self._checked_channel_ids() or None
        if channel_ids:
            self._append_log(f"Collecting only {len(channel_ids)} checked channel(s).")

        self._collect_worker = CollectWorker(
            kind=self.kind_combo.currentText(),
            name_contains=self.name_contains_edit.text().strip() or None,
            full_history=self.full_history_checkbox.isChecked(),
            channel_ids=channel_ids,
            since=since,
            until=until,
            collect_threads=self.threads_checkbox.isChecked(),
        )
        self._collect_worker.finished_ok.connect(self._on_collect_finished)
        self._collect_worker.failed.connect(self._on_collect_failed)
        self._collect_worker.finished.connect(lambda: self._set_busy(False))
        self._collect_worker.start()

    def _on_collect_finished(self, channel_count: int) -> None:
        self._append_log(f"Done. Visited {channel_count} channel(s).")

    def _on_collect_failed(self, message: str) -> None:
        self._append_log(f"Collect failed: {message}")
