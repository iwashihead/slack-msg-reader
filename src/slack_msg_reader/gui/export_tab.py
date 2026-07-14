from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from slack_msg_reader import export as export_module
from slack_msg_reader.config import DATA_DIR
from slack_msg_reader.gui.workers import ExportWorker


class ExportTab(QWidget):
    def __init__(self):
        super().__init__()
        self._worker: ExportWorker | None = None

        layout = QVBoxLayout(self)

        filter_box = QGroupBox("Filters")
        form = QFormLayout(filter_box)

        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("(optional) exact channel name")
        form.addRow("Channel:", self.channel_edit)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("(optional) sender display name")
        form.addRow("User:", self.user_edit)

        since_row = QHBoxLayout()
        self.since_checkbox = QCheckBox("Since:")
        self.since_edit = QDateEdit(calendarPopup=True)
        self.since_edit.setDate(datetime.now().date().replace(day=1))
        self.since_edit.setEnabled(False)
        self.since_checkbox.toggled.connect(self.since_edit.setEnabled)
        since_row.addWidget(self.since_checkbox)
        since_row.addWidget(self.since_edit)
        form.addRow(since_row)

        until_row = QHBoxLayout()
        self.until_checkbox = QCheckBox("Until:")
        self.until_edit = QDateEdit(calendarPopup=True)
        self.until_edit.setDate(datetime.now().date())
        self.until_edit.setEnabled(False)
        self.until_checkbox.toggled.connect(self.until_edit.setEnabled)
        until_row.addWidget(self.until_checkbox)
        until_row.addWidget(self.until_edit)
        form.addRow(until_row)

        self.max_chars_spin = QSpinBox()
        self.max_chars_spin.setRange(1_000, 10_000_000)
        self.max_chars_spin.setSingleStep(10_000)
        self.max_chars_spin.setValue(export_module.DEFAULT_MAX_CHARS)
        form.addRow("Max chars/file:", self.max_chars_spin)

        self.max_files_spin = QSpinBox()
        self.max_files_spin.setRange(1, 100)
        self.max_files_spin.setValue(export_module.DEFAULT_MAX_FILES)
        form.addRow("Max files:", self.max_files_spin)

        output_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit(str(DATA_DIR / "exports"))
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_output_dir)
        output_row.addWidget(self.output_dir_edit, 1)
        output_row.addWidget(browse_button)
        form.addRow("Output dir:", output_row)

        layout.addWidget(filter_box)

        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self._start_export)
        layout.addWidget(self.export_button)

        result_box = QGroupBox("Result")
        result_layout = QVBoxLayout(result_box)
        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        result_layout.addWidget(self.result_view)
        layout.addWidget(result_box, 1)

    def _browse_output_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose output directory", self.output_dir_edit.text())
        if chosen:
            self.output_dir_edit.setText(chosen)

    def _start_export(self) -> None:
        since = None
        if self.since_checkbox.isChecked():
            d = self.since_edit.date().toPython()
            since = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)

        until = None
        if self.until_checkbox.isChecked():
            d = self.until_edit.date().toPython()
            until = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1, microseconds=-1)

        self.export_button.setEnabled(False)
        self.result_view.setPlainText("Exporting...")
        self._worker = ExportWorker(
            output_dir=Path(self.output_dir_edit.text()),
            channel=self.channel_edit.text().strip() or None,
            user=self.user_edit.text().strip() or None,
            since=since,
            until=until,
            max_chars=self.max_chars_spin.value(),
            max_files=self.max_files_spin.value(),
        )
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(lambda: self.export_button.setEnabled(True))
        self._worker.start()

    def _on_finished(self, paths: list, truncated: bool) -> None:
        if not paths:
            self.result_view.setPlainText("No messages matched the given filters.")
            return
        lines = [f"Wrote {p} ({p.stat().st_size:,} bytes)" for p in paths]
        if truncated:
            lines.append(
                f"Warning: content still exceeds {self.max_files_spin.value()} files even after growing "
                "the per-file budget; increase Max files or narrow the filters."
            )
        self.result_view.setPlainText("\n".join(lines))

    def _on_failed(self, message: str) -> None:
        self.result_view.setPlainText(f"Export failed: {message}")
