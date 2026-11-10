"""Convert tab: turn local media files into another format with the bundled FFmpeg."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import convert, engine
from . import theme
from .config import Config
from .widgets import button, card, centered, height_label, label, open_folder, repolish, reveal, select_data
from .workers import ConvertWorker

C_NAME, C_FOLDER, C_TARGET, C_PROG, C_ACT = range(5)
ACTIVE = ("queued", "running")


@dataclass
class ConvRow:
    key: int
    src: str
    state: str = "idle"
    out: str = ""
    worker: ConvertWorker | None = None


class ConvertTab(QWidget):
    log = Signal(str)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.cfg = config
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.rows: list[ConvRow] = []
        self._next = 1
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(self._build_options())
        root.addWidget(self._build_list(), 1)
        self._target_changed()

    def _build_options(self):
        c = card()
        g = QGridLayout(c)
        g.setContentsMargins(16, 14, 16, 14)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        g.addWidget(label("CONVERT LOCAL FILES", "sectionTitle"), 0, 0, 1, 6)
        g.addWidget(label("Drop audio or video files below — or add them — and pick what to turn them into. "
                          "Everything runs locally with FFmpeg.", "muted", wrap=True), 1, 0, 1, 6)

        self.target = QComboBox()
        for t in convert.TARGETS:
            self.target.addItem(("🎵 " if engine.is_audio(t) else "🎬 ") + engine.FORMAT_LABELS[t], t)
        select_data(self.target, self.cfg.get("conv_target"))
        self.target.currentIndexChanged.connect(lambda _i: self._target_changed())
        g.addWidget(label("Convert to"), 2, 0)
        g.addWidget(self.target, 2, 1)

        self.quality = QComboBox()
        self.qual_lbl = label("Quality")
        g.addWidget(self.qual_lbl, 2, 2)
        g.addWidget(self.quality, 2, 3)

        self.copy_chk = QCheckBox("Fast copy (no re-encode)")
        self.copy_chk.setToolTip("Only changes the container (e.g. MKV → MP4). Instant and lossless,\n"
                                 "but fails if the codecs don't fit the new container.")
        self.copy_chk.toggled.connect(lambda _on: self.quality.setEnabled(not self.copy_chk.isChecked()
                                                                          and self._quality_applies()))
        g.addWidget(self.copy_chk, 2, 4, 1, 2)

        self.same_chk = QCheckBox("Save next to the original")
        self.same_chk.setChecked(self.cfg.get("conv_same_folder"))
        self.same_chk.toggled.connect(self._same_toggled)
        g.addWidget(self.same_chk, 3, 0, 1, 2)
        self.out_input = QLineEdit(self.cfg.get("conv_outdir") or Config.default_dest())
        g.addWidget(self.out_input, 3, 2, 1, 2)
        self.browse_btn = button("Browse…")
        self.browse_btn.clicked.connect(self._browse)
        g.addWidget(self.browse_btn, 3, 4)
        self._same_toggled(self.same_chk.isChecked())
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        return c

    def _build_list(self):
        c = card()
        v = QVBoxLayout(c)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)
        bar = QHBoxLayout()
        bar.addWidget(label("FILES", "sectionTitle"))
        self.count_lbl = label("empty", "pill")
        bar.addWidget(self.count_lbl)
        bar.addStretch(1)
        add = button("＋ Add files…")
        add.clicked.connect(self._add_dialog)
        bar.addWidget(add)
        clear = button("Clear finished")
        clear.clicked.connect(self._clear)
        bar.addWidget(clear)
        v.addLayout(bar)

        self.stack = QStackedWidget()
        drop = QLabel("⤓\n\nDrop audio or video files here\n\nMP4 · MKV · MOV · AVI · WebM · MP3 · M4A · WAV · FLAC · OGG …")
        drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop.setObjectName("dropZone")
        self.stack.addWidget(drop)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["FILE", "FOLDER", "TO", "PROGRESS", ""])
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(44)
        hh = self.table.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setSectionResizeMode(C_NAME, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(C_FOLDER, QHeaderView.ResizeMode.Stretch)
        for col, w in ((C_TARGET, 80), (C_PROG, 240), (C_ACT, 84)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, w)
        self.stack.addWidget(self.table)
        v.addWidget(self.stack, 1)

        foot = QHBoxLayout()
        self.overall_lbl = label("Ready", "muted")
        foot.addWidget(self.overall_lbl, 1)
        self.cancel_btn = button("Cancel all", "danger")
        self.cancel_btn.clicked.connect(self.cancel_all)
        foot.addWidget(self.cancel_btn)
        self.go_btn = button("🔄  Convert", "primary")
        self.go_btn.setMinimumWidth(200)
        self.go_btn.clicked.connect(self.start)
        foot.addWidget(self.go_btn)
        v.addLayout(foot)
        self._refresh()
        return c

    # ----------------------------------------------------------------- options

    def _quality_applies(self) -> bool:
        t = self.target.currentData()
        return t not in engine.LOSSLESS

    def _target_changed(self):
        t = self.target.currentData()
        self.cfg.set("conv_target", t)
        self.quality.clear()
        audio = engine.is_audio(t)
        self.qual_lbl.setText("Bitrate" if audio else "Max height")
        if audio:
            if t in engine.LOSSLESS:
                self.quality.addItem("Lossless", 0)
            else:
                for k in engine.AUDIO_BITRATES:
                    self.quality.addItem(f"{k} kbps", k)
                select_data(self.quality, convert.DEFAULT_KBPS.get(t, 320))
        else:
            self.quality.addItem("Keep original", 0)
            for h in (2160, 1440, 1080, 720, 480, 360):
                self.quality.addItem(height_label(h), h)
        self.copy_chk.setEnabled(not audio)
        if audio:
            self.copy_chk.setChecked(False)
        self.quality.setEnabled(self._quality_applies() and not self.copy_chk.isChecked())

    def _same_toggled(self, on: bool):
        self.cfg.set("conv_same_folder", on)
        self.out_input.setEnabled(not on)
        self.browse_btn.setEnabled(not on)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose output folder", self.out_input.text())
        if d:
            self.out_input.setText(d)
            self.cfg.set("conv_outdir", d)

    # ----------------------------------------------------------------- files

    def add_files(self, files: list[str]):
        known = {r.src for r in self.rows}
        added = 0
        for f in files:
            p = Path(f)
            if p.is_dir():
                added += self.add_files([str(x) for x in sorted(p.iterdir()) if x.suffix.lower() in convert.MEDIA_EXTS])
                known = {r.src for r in self.rows}
                continue
            if not p.is_file() or str(p) in known:
                continue
            row = ConvRow(self._next, str(p))
            self._next += 1
            self.rows.append(row)
            self._add_row(row)
            known.add(str(p))
            added += 1
        self._refresh()
        return added

    def _add_dialog(self):
        exts = " ".join(f"*{e}" for e in sorted(convert.MEDIA_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, "Add media files", "", f"Media files ({exts});;All files (*)")
        if files:
            self.add_files(files)

    def _add_row(self, row: ConvRow):
        i = self.table.rowCount()
        self.table.insertRow(i)
        p = Path(row.src)
        name = QTableWidgetItem(p.name)
        name.setToolTip(str(p))
        self.table.setItem(i, C_NAME, name)
        folder = QTableWidgetItem(str(p.parent))
        folder.setForeground(QColor(theme.MUTED))
        self.table.setItem(i, C_FOLDER, folder)
        tgt = QTableWidgetItem("—")
        tgt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(i, C_TARGET, tgt)
        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setFormat("Ready")
        bar.setValue(0)
        self.table.setCellWidget(i, C_PROG, centered(bar))
        opn = button("Open", "cellBtn")
        opn.setEnabled(False)
        opn.clicked.connect(lambda _c=False, k=row.key: self._open(k))
        self.table.setCellWidget(i, C_ACT, centered(opn))

    def _idx(self, key: int) -> int:
        return next((i for i, r in enumerate(self.rows) if r.key == key), -1)

    def _bar(self, i: int) -> QProgressBar:
        return self.table.cellWidget(i, C_PROG).property("inner")

    def _open(self, key: int):
        i = self._idx(key)
        if i >= 0 and self.rows[i].out:
            reveal(self.rows[i].out)

    def _clear(self):
        for i in range(len(self.rows) - 1, -1, -1):
            if self.rows[i].state == "done":
                self.table.removeRow(i)
                del self.rows[i]
        self._refresh()

    # ----------------------------------------------------------------- run

    def _options(self) -> convert.ConvertOptions:
        outdir = None
        if not self.same_chk.isChecked():
            outdir = self.out_input.text().strip() or Config.default_dest()
            self.cfg.set("conv_outdir", outdir)
        return convert.ConvertOptions(
            target=self.target.currentData(),
            quality=self.quality.currentData() or 0,
            copy_streams=self.copy_chk.isChecked() and self.copy_chk.isEnabled(),
            outdir=outdir,
        )

    def start(self):
        opts = self._options()
        n = 0
        for i, row in enumerate(self.rows):
            if row.state in ACTIVE or row.state == "done":
                continue
            w = ConvertWorker(row.key, row.src, opts)
            w.signals.progress.connect(self._progress)
            w.signals.finished.connect(self._finished)
            w.signals.failed.connect(self._failed)
            w.signals.log.connect(self.log)
            row.worker, row.state = w, "queued"
            self.table.item(i, C_TARGET).setText(opts.target.upper())
            self._set(i, 0, "Queued", "")
            self.pool.start(w)
            n += 1
        self.overall_lbl.setText(f"Converting {n} file{'s' if n != 1 else ''}…" if n else "Nothing to convert — add files first.")
        self._refresh()

    def cancel_all(self):
        for row in self.rows:
            if row.state in ACTIVE and row.worker:
                row.worker.cancel.set()
                if row.state == "queued" and self.pool.tryTake(row.worker):
                    self._failed(row.key, "Cancelled")

    def active_count(self) -> int:
        return sum(1 for r in self.rows if r.state in ACTIVE)

    def _progress(self, key: int, p: engine.Progress):
        i = self._idx(key)
        if i < 0:
            return
        self.rows[i].state = "running"
        bar = self._bar(i)
        if p.fraction is not None:
            bar.setValue(int(p.fraction * 1000))
        bar.setFormat(p.text)
        self._refresh()

    def _finished(self, key: int, out: str):
        i = self._idx(key)
        if i < 0:
            return
        row = self.rows[i]
        row.state, row.out, row.worker = "done", out, None
        self._set(i, 1000, "✓ " + Path(out).name, "done", tip=out)
        self.table.cellWidget(i, C_ACT).property("inner").setEnabled(True)
        self.log.emit(f"Converted: {out}")
        self._refresh()

    def _failed(self, key: int, msg: str):
        i = self._idx(key)
        if i < 0:
            return
        row = self.rows[i]
        cancelled = msg == "Cancelled"
        row.state, row.worker = ("cancelled" if cancelled else "error"), None
        self._set(i, 0 if cancelled else 1000, "Cancelled" if cancelled else f"✕ {msg}", "error", tip=msg)
        if not cancelled:
            self.log.emit(f"Convert failed: {row.src} — {msg}")
        self._refresh()

    def _set(self, i, value, text, state, tip=""):
        bar = self._bar(i)
        bar.setValue(value)
        bar.setFormat(text)
        bar.setToolTip(tip or text)
        bar.setProperty("state", state)
        repolish(bar)

    def _refresh(self):
        total = len(self.rows)
        self.stack.setCurrentIndex(1 if total else 0)
        self.count_lbl.setText(f"{total} file{'s' if total != 1 else ''}" if total else "empty")
        active = self.active_count()
        self.cancel_btn.setEnabled(bool(active))
        pending = sum(1 for r in self.rows if r.state not in ACTIVE and r.state != "done")
        self.go_btn.setEnabled(pending > 0)
        self.go_btn.setText(f"🔄  Convert {pending} file{'s' if pending != 1 else ''}" if pending else "🔄  Convert")
        if not active and total:
            done = sum(1 for r in self.rows if r.state == "done")
            failed = sum(1 for r in self.rows if r.state == "error")
            if done or failed:
                self.overall_lbl.setText(f"Finished — {done} converted" + (f", {failed} failed" if failed else ""))

    # ----------------------------------------------------------------- drag & drop

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self.add_files(files)
            e.acceptProposedAction()

    def open_output(self):
        open_folder(self.out_input.text())
