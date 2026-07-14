import pandas as pd
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from slack_msg_reader.analysis import queries
from slack_msg_reader.gui.models import PandasTableModel

# Which optional param widgets each report type actually uses.
_REPORT_PARAMS = {
    "channels": set(),
    "users": {"channel"},
    "hourly": set(),
    "weekday": set(),
    "threads": {"limit"},
    "reactions": {"limit"},
    "words": {"limit"},
    "search": {"keyword", "limit"},
}


class AnalyzeTab(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        form_box = QGroupBox("Report")
        form = QFormLayout(form_box)

        self.report_combo = QComboBox()
        self.report_combo.addItems(list(_REPORT_PARAMS.keys()))
        self.report_combo.currentTextChanged.connect(self._update_param_enabled_state)
        form.addRow("Type:", self.report_combo)

        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("(users report) exact channel name")
        form.addRow("Channel:", self.channel_edit)

        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("(search report) text to find")
        form.addRow("Keyword:", self.keyword_edit)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 10_000)
        self.limit_spin.setValue(20)
        form.addRow("Limit:", self.limit_spin)

        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self._run)
        form.addRow(self.run_button)

        layout.addWidget(form_box)

        self.table_view = QTableView()
        self.table_model = PandasTableModel()
        self.table_view.setModel(self.table_model)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_view, 1)

        self._update_param_enabled_state(self.report_combo.currentText())

    def _update_param_enabled_state(self, report: str) -> None:
        used = _REPORT_PARAMS.get(report, set())
        self.channel_edit.setEnabled("channel" in used)
        self.keyword_edit.setEnabled("keyword" in used)
        self.limit_spin.setEnabled("limit" in used)

    def _run(self) -> None:
        report = self.report_combo.currentText()
        limit = self.limit_spin.value()
        keyword = self.keyword_edit.text().strip()
        channel = self.channel_edit.text().strip() or None

        if report == "channels":
            df = queries.messages_per_channel()
        elif report == "users":
            df = queries.messages_per_user(channel_name=channel)
        elif report == "hourly":
            df = queries.activity_by_hour()
        elif report == "weekday":
            df = queries.activity_by_weekday()
        elif report == "threads":
            df = queries.reply_thread_leaderboard(limit=limit)
        elif report == "reactions":
            df = queries.reaction_leaderboard(limit=limit)
        elif report == "words":
            df = queries.top_words(top_n=limit)
        elif report == "search":
            if not keyword:
                self.table_model.set_dataframe(pd.DataFrame({"message": ["Enter a keyword to search."]}))
                return
            df = queries.keyword_search(keyword, limit=limit)
        else:
            return

        self.table_model.set_dataframe(df)
