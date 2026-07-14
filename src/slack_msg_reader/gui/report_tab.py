from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from slack_msg_reader.analysis.queries import list_known_users
from slack_msg_reader.config import DATA_DIR
from slack_msg_reader.gui.workers import ReportWorker


def _this_week_range() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday, now


class ReportTab(QWidget):
    """Full-context conversation export for one participant + a companion AI
    analysis prompt (what they did, new tasks/deadlines, poor communication,
    unanswered items). Deliberately does not call any AI API -- the prompt
    is meant to be pasted into whatever chatbot the user already uses,
    alongside the exported conversation file(s).
    """

    def __init__(self):
        super().__init__()
        self._worker: ReportWorker | None = None
        self._last_prompt_path: Path | None = None

        layout = QVBoxLayout(self)

        intro = QPlainTextEdit(
            "特定の人が関わった会話を、期間で絞り込んでチャンネル/DMごとにまとめて出力します。\n"
            "その人自身の発言だけでなく、同じ会話の相手からの発言も含めて出力するので、\n"
            "文脈込みでAIチャットボットに読ませて分析させることができます。\n"
            "(このアプリ自体はAI APIを呼び出しません。出力されたファイルを自分でAIに渡してください)"
        )
        intro.setReadOnly(True)
        intro.setMaximumHeight(90)
        layout.addWidget(intro)

        form_box = QGroupBox("対象")
        form = QFormLayout(form_box)

        self.user_combo = QComboBox()
        self.user_combo.setEditable(True)
        self._refresh_users_button = QPushButton("一覧を更新")
        self._refresh_users_button.clicked.connect(self._reload_known_users)
        user_row = QHBoxLayout()
        user_row.addWidget(self.user_combo, 1)
        user_row.addWidget(self._refresh_users_button)
        form.addRow("ユーザー:", user_row)
        self._reload_known_users()

        since_row = QHBoxLayout()
        self.since_checkbox = QCheckBox("開始日:")
        self.since_edit = QDateEdit(calendarPopup=True)
        self.since_edit.setDate(datetime.now().date().replace(day=1))
        self.since_edit.setEnabled(False)
        self.since_checkbox.toggled.connect(self.since_edit.setEnabled)
        since_row.addWidget(self.since_checkbox)
        since_row.addWidget(self.since_edit)
        form.addRow(since_row)

        until_row = QHBoxLayout()
        self.until_checkbox = QCheckBox("終了日:")
        self.until_edit = QDateEdit(calendarPopup=True)
        self.until_edit.setDate(datetime.now().date())
        self.until_edit.setEnabled(False)
        self.until_checkbox.toggled.connect(self.until_edit.setEnabled)
        until_row.addWidget(self.until_checkbox)
        until_row.addWidget(self.until_edit)
        form.addRow(until_row)

        this_week_button = QPushButton("今週 (月曜〜現在) を指定")
        this_week_button.clicked.connect(self._set_this_week)
        form.addRow(this_week_button)

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
        self.output_dir_edit = QLineEdit(str(DATA_DIR / "reports"))
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_output_dir)
        output_row.addWidget(self.output_dir_edit, 1)
        output_row.addWidget(browse_button)
        form.addRow("Output dir:", output_row)

        layout.addWidget(form_box)

        self.generate_button = QPushButton("Generate")
        self.generate_button.clicked.connect(self._start_generate)
        layout.addWidget(self.generate_button)

        result_box = QGroupBox("Result")
        result_layout = QVBoxLayout(result_box)
        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        result_layout.addWidget(self.result_view)
        self.copy_prompt_button = QPushButton("プロンプトをクリップボードにコピー")
        self.copy_prompt_button.setEnabled(False)
        self.copy_prompt_button.clicked.connect(self._copy_prompt)
        result_layout.addWidget(self.copy_prompt_button)
        layout.addWidget(result_box, 1)

    def _reload_known_users(self) -> None:
        current = self.user_combo.currentText()
        self.user_combo.clear()
        try:
            self.user_combo.addItems(list_known_users())
        except Exception:
            pass  # DB may not be initialized yet -- editable combo still works
        if current:
            self.user_combo.setCurrentText(current)

    def _set_this_week(self) -> None:
        since, until = _this_week_range()
        self.since_checkbox.setChecked(True)
        self.until_checkbox.setChecked(True)
        self.since_edit.setDate(since.date())
        self.until_edit.setDate(until.date())

    def _browse_output_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose output directory", self.output_dir_edit.text())
        if chosen:
            self.output_dir_edit.setText(chosen)

    def _start_generate(self) -> None:
        participant = self.user_combo.currentText().strip()
        if not participant:
            self.result_view.setPlainText("ユーザーを指定してください。")
            return

        since = None
        if self.since_checkbox.isChecked():
            d = self.since_edit.date().toPython()
            since = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)

        until = None
        if self.until_checkbox.isChecked():
            d = self.until_edit.date().toPython()
            until = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1, microseconds=-1)

        self.generate_button.setEnabled(False)
        self.copy_prompt_button.setEnabled(False)
        self._last_prompt_path = None
        self.result_view.setPlainText("Generating...")
        self._worker = ReportWorker(
            output_dir=Path(self.output_dir_edit.text()),
            participant=participant,
            since=since,
            until=until,
            max_chars=self.max_chars_spin.value(),
            max_files=self.max_files_spin.value(),
        )
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(lambda: self.generate_button.setEnabled(True))
        self._worker.start()

    def _on_finished(self, result) -> None:
        if not result.conversation_files:
            self.result_view.setPlainText("指定した条件に一致するメッセージが見つかりませんでした。")
            return

        lines = [f"Wrote {p} ({p.stat().st_size:,} bytes)" for p in result.conversation_files]
        lines.append(f"Wrote {result.prompt_file}")
        if result.truncated:
            lines.append(
                f"Warning: content still exceeds {self.max_files_spin.value()} files even after growing "
                "the per-file budget; increase Max files or narrow the date range."
            )
        self.result_view.setPlainText("\n".join(lines))
        self._last_prompt_path = result.prompt_file
        self.copy_prompt_button.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self.result_view.setPlainText(f"Failed: {message}")

    def _copy_prompt(self) -> None:
        if not self._last_prompt_path:
            return
        text = self._last_prompt_path.read_text(encoding="utf-8")
        QGuiApplication.clipboard().setText(text)
