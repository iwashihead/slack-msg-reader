"""QThread workers wrapping potentially-slow calls so they never freeze the
Qt event loop. Each worker reports success/failure through signals rather
than return values or exceptions (exceptions raised inside QThread.run()
are not propagated to the caller)."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from slack_msg_reader import export as export_module
from slack_msg_reader import report as report_module
from slack_msg_reader.collect import run_collect, run_collect_for_user, run_inspect
from slack_msg_reader.scraper import chrome_launcher
from slack_msg_reader.scraper.browser import SlackTabNotFoundError


class ChromeWorker(QThread):
    finished_ok = Signal(bool)  # True once CDP responds
    failed = Signal(str)

    def run(self) -> None:
        try:
            ready = chrome_launcher.launch()
        except chrome_launcher.ChromeNotFoundError as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(ready)


class InspectWorker(QThread):
    finished_ok = Signal(str, list)  # (page_url, channels)
    failed = Signal(str)

    def run(self) -> None:
        try:
            url, channels = run_inspect()
        except SlackTabNotFoundError as e:
            self.failed.emit(str(e))
            return
        except Exception as e:  # noqa: BLE001 -- surface anything unexpected to the UI instead of crashing the thread silently
            self.failed.emit(f"Unexpected error: {e}")
            return
        self.finished_ok.emit(url, channels)


class CollectWorker(QThread):
    finished_ok = Signal(int)  # number of channels visited
    failed = Signal(str)

    def __init__(
        self,
        kind: str = "all",
        name_contains: str | None = None,
        full_history: bool = False,
        channel_ids: list[str] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        collect_threads: bool = True,
    ):
        super().__init__()
        self.kind = kind
        self.name_contains = name_contains
        self.full_history = full_history
        self.channel_ids = channel_ids
        self.since = since
        self.until = until
        self.collect_threads = collect_threads

    def run(self) -> None:
        try:
            count = run_collect(
                kind=self.kind,
                name_contains=self.name_contains,
                full_history=self.full_history,
                channel_ids=self.channel_ids,
                since=self.since,
                until=self.until,
                collect_threads=self.collect_threads,
            )
        except SlackTabNotFoundError as e:
            self.failed.emit(str(e))
            return
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Unexpected error: {e}")
            return
        self.finished_ok.emit(count)


class UserCollectWorker(QThread):
    """Wraps run_collect_for_user -- the from:<@user> search-based collect
    mode, as an alternative to CollectWorker's per-channel scan."""

    finished_ok = Signal(int)  # number of messages stored
    failed = Signal(str)

    def __init__(self, user: str):
        super().__init__()
        self.user = user

    def run(self) -> None:
        try:
            count = run_collect_for_user(self.user)
        except SlackTabNotFoundError as e:
            self.failed.emit(str(e))
            return
        except ValueError as e:
            self.failed.emit(str(e))
            return
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Unexpected error: {e}")
            return
        self.finished_ok.emit(count)


class ExportWorker(QThread):
    finished_ok = Signal(list, bool)  # (written file paths, truncated_warning)
    failed = Signal(str)

    def __init__(
        self,
        output_dir: Path,
        channel: str | None = None,
        user: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        max_chars: int = export_module.DEFAULT_MAX_CHARS,
        max_files: int = export_module.DEFAULT_MAX_FILES,
    ):
        super().__init__()
        self.output_dir = output_dir
        self.channel = channel
        self.user = user
        self.since = since
        self.until = until
        self.max_chars = max_chars
        self.max_files = max_files

    def run(self) -> None:
        try:
            paths, truncated = export_module.write_export(
                self.output_dir,
                channel=self.channel,
                user=self.user,
                since=self.since,
                until=self.until,
                max_chars=self.max_chars,
                max_files=self.max_files,
            )
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Unexpected error: {e}")
            return
        self.finished_ok.emit(paths, truncated)


class ReportWorker(QThread):
    finished_ok = Signal(object)  # report.ReportResult
    failed = Signal(str)

    def __init__(
        self,
        output_dir: Path,
        participant: str,
        since: datetime | None = None,
        until: datetime | None = None,
        max_chars: int = export_module.DEFAULT_MAX_CHARS,
        max_files: int = export_module.DEFAULT_MAX_FILES,
    ):
        super().__init__()
        self.output_dir = output_dir
        self.participant = participant
        self.since = since
        self.until = until
        self.max_chars = max_chars
        self.max_files = max_files

    def run(self) -> None:
        try:
            result = report_module.generate_report(
                self.output_dir,
                participant=self.participant,
                since=self.since,
                until=self.until,
                max_chars=self.max_chars,
                max_files=self.max_files,
            )
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Unexpected error: {e}")
            return
        self.finished_ok.emit(result)
