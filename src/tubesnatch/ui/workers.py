"""Background workers bridging the engine to Qt signals."""

from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, QRunnable, Signal

from .. import engine


class ProbeSignals(QObject):
    done = Signal(object)  # ProbeResult
    failed = Signal(str)
    log = Signal(str)


class ProbeWorker(QRunnable):
    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self.signals = ProbeSignals()

    def run(self) -> None:
        try:
            self.signals.done.emit(engine.probe(self.url, log=self.signals.log.emit))
        except Exception as e:  # noqa: BLE001 - surfaced to the user
            self.signals.failed.emit(_clean(e))


class DownloadSignals(QObject):
    progress = Signal(int, object)  # row key, engine.Progress
    finished = Signal(int, str)  # row key, file path
    failed = Signal(int, str)  # row key, message
    log = Signal(str)


class DownloadWorker(QRunnable):
    def __init__(self, key: int, url: str, options: engine.JobOptions):
        super().__init__()
        self.key = key
        self.url = url
        self.options = options
        self.cancel = threading.Event()
        self.signals = DownloadSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        if self.cancel.is_set():
            self.signals.failed.emit(self.key, "Cancelled")
            return
        try:
            path = engine.download(
                self.url,
                self.options,
                lambda p: self.signals.progress.emit(self.key, p),
                self.cancel,
                log=self.signals.log.emit,
            )
            self.signals.finished.emit(self.key, path)
        except Exception as e:  # noqa: BLE001
            if self.cancel.is_set():
                self.signals.failed.emit(self.key, "Cancelled")
            else:
                self.signals.log.emit(traceback.format_exc(limit=3))
                self.signals.failed.emit(self.key, _clean(e))


def _clean(e: Exception) -> str:
    msg = str(e).strip() or e.__class__.__name__
    msg = msg.replace("ERROR: ", "")
    # strip ANSI colour codes yt-dlp may add
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", msg)
