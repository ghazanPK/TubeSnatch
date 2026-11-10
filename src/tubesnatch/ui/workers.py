"""Background workers bridging the engine to Qt signals."""

from __future__ import annotations

import re
import threading
import traceback
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from .. import convert, engine


def clean_error(e: BaseException) -> str:
    msg = str(e).strip() or e.__class__.__name__
    msg = msg.replace("ERROR: ", "")
    return re.sub(r"\x1b\[[0-9;]*m", "", msg)


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
            self.signals.failed.emit(clean_error(e))


class JobSignals(QObject):
    progress = Signal(int, object)  # row key, engine.Progress
    finished = Signal(int, object)  # row key, result (DownloadResult | str)
    failed = Signal(int, str)  # row key, message
    log = Signal(str)


class DownloadWorker(QRunnable):
    def __init__(self, key: int, url: str, options: engine.JobOptions):
        super().__init__()
        self.key = key
        self.url = url
        self.options = options
        self.cancel = threading.Event()
        self.signals = JobSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        if self.cancel.is_set():
            self.signals.failed.emit(self.key, "Cancelled")
            return
        try:
            res = engine.download(
                self.url, self.options, lambda p: self.signals.progress.emit(self.key, p), self.cancel,
                log=self.signals.log.emit,
            )
            self.signals.finished.emit(self.key, res)
        except Exception as e:  # noqa: BLE001
            if self.cancel.is_set():
                self.signals.failed.emit(self.key, "Cancelled")
            else:
                self.signals.log.emit(traceback.format_exc(limit=3))
                self.signals.failed.emit(self.key, clean_error(e))


class ConvertWorker(QRunnable):
    def __init__(self, key: int, src: str, options: convert.ConvertOptions):
        super().__init__()
        self.key = key
        self.src = src
        self.options = options
        self.cancel = threading.Event()
        self.signals = JobSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        if self.cancel.is_set():
            self.signals.failed.emit(self.key, "Cancelled")
            return
        try:
            def prog(frac):
                text = f"Converting… {int(frac * 100)}%" if frac is not None else "Converting…"
                self.signals.progress.emit(self.key, engine.Progress(frac, text))

            prog(None)
            out = convert.convert(self.src, self.options, prog, self.cancel)
            self.signals.finished.emit(self.key, out)
        except Exception as e:  # noqa: BLE001
            if self.cancel.is_set():
                self.signals.failed.emit(self.key, "Cancelled")
            else:
                self.signals.log.emit(traceback.format_exc(limit=3))
                self.signals.failed.emit(self.key, clean_error(e))


class TaskSignals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(object)  # float | None


class TaskWorker(QRunnable):
    """Run any callable off the UI thread. If ``fn`` accepts ``progress=``, it gets a callback."""

    def __init__(self, fn: Callable, *args, with_progress: bool = False, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.with_progress = with_progress
        self.signals = TaskSignals()

    def run(self) -> None:
        try:
            if self.with_progress:
                self.kwargs["on_progress"] = self.signals.progress.emit
            self.signals.done.emit(self.fn(*self.args, **self.kwargs))
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(clean_error(e))
