from PySide6.QtWidgets import QMainWindow, QTabWidget

from slack_msg_reader.gui.analyze_tab import AnalyzeTab
from slack_msg_reader.gui.chrome_tab import ChromeCollectTab
from slack_msg_reader.gui.export_tab import ExportTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("slack-msg-reader")
        self.resize(900, 700)

        tabs = QTabWidget()
        tabs.addTab(ChromeCollectTab(), "Chrome && Collect")
        tabs.addTab(ExportTab(), "Export")
        tabs.addTab(AnalyzeTab(), "Analyze")
        self.setCentralWidget(tabs)
