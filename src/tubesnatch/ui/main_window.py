"""Main application window."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, engine, paths
from . import theme
from .about import AboutDialog
from .workers import DownloadWorker, ProbeWorker

THUMB_W, THUMB_H = 96, 54
HERO_W, HERO_H = 208, 117

C_CHECK, C_THUMB, C_IDX, C_TITLE, C_DUR, C_MODE, C_QUAL, C_PROG, C_ACT = range(9)
HEADERS = ["", "", "#", "TITLE", "LENGTH", "FORMAT", "QUALITY", "PROGRESS", ""]


@dataclass
class Row:
    key: int
    entry: engine.Entry
    playlist_title: str | None
    mode: str
    quality: int
    state: str = "idle"  # idle | queued | running | done | error | cancelled
    path: str = ""
    worker: DownloadWorker | None = None


# --------------------------------------------------------------------------- small widgets


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    shadow = QGraphicsDropShadowEffect(f)
    shadow.setBlurRadius(28)
    shadow.setOffset(0, 6)
    shadow.setColor(QColor(0, 0, 0, 110))
    f.setGraphicsEffect(shadow)
    return f


def label(text: str = "", name: str | None = None) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    return lb


def button(text: str, name: str | None = None, tip: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def rounded(pix: QPixmap, w: int, h: int, radius: int) -> QPixmap:
    scaled = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = (scaled.width() - w) // 2
    y = (scaled.height() - h) // 2
    scaled = scaled.copy(x, y, w, h)
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, scaled)
    p.end()
    return out


def placeholder_pix(w: int, h: int, radius: int) -> QPixmap:
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.SURFACE_2))
    p.drawRoundedRect(0, 0, w, h, radius, radius)
    p.end()
    return out


class ThumbLoader:
    """Async thumbnail fetcher with an in-memory cache."""

    def __init__(self, parent):
        self.nam = QNetworkAccessManager(parent)
        self.cache: dict[str, QPixmap] = {}
        self.waiting: dict[str, list] = {}

    def get(self, url: str | None, callback) -> None:
        if not url:
            return
        if url in self.cache:
            callback(self.cache[url])
            return
        if url in self.waiting:
            self.waiting[url].append(callback)
            return
        self.waiting[url] = [callback]
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"TubeSnatch/{__version__}")
        reply = self.nam.get(req)
        reply.finished.connect(lambda r=reply, u=url: self._done(r, u))

    def _done(self, reply: QNetworkReply, url: str) -> None:
        pix = QPixmap()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pix.loadFromData(reply.readAll())
        reply.deleteLater()
        callbacks = self.waiting.pop(url, [])
        if pix.isNull():
            return
        self.cache[url] = pix
        for cb in callbacks:
            try:
                cb(pix)
            except RuntimeError:  # widget already deleted
                pass


# --------------------------------------------------------------------------- window


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TubeSnatch — video & playlist downloader")
        self.setWindowIcon(QIcon(str(paths.asset("icon.svg"))))
        self.resize(1240, 820)
        self.setMinimumSize(1100, 680)
        self.setAcceptDrops(True)

        self.settings = QSettings("TubeSnatch", "TubeSnatch")
        self.thumbs = ThumbLoader(self)
        self.probe_pool = QThreadPool(self)
        self.probe_pool.setMaxThreadCount(2)
        self.dl_pool = QThreadPool(self)
        self.rows: list[Row] = []
        self._next_key = 1
        self._probing = 0

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 12)
        root.setSpacing(14)

        top = self._build_header()
        top.insertWidget(2, self._build_url_card(), 1)
        root.addLayout(top)

        mid = QHBoxLayout()
        mid.setSpacing(14)
        mid.addWidget(self._build_hero_card(), 2)
        mid.addWidget(self._build_options_card(), 3)
        root.addLayout(mid)

        root.addWidget(self._build_list_card(), 1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.log_view.setFixedHeight(150)
        self.log_view.hide()
        root.addWidget(self.log_view)

        self._build_statusbar()
        self._load_settings()
        self._update_mode_widgets()
        self._refresh_counts()
        self._check_tools()

    # ----------------------------------------------------------------- layout builders

    def _build_header(self):
        h = QHBoxLayout()
        h.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(QIcon(str(paths.asset("icon.svg"))).pixmap(44, 44))
        h.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        brand = label("TubeSnatch", "brand")
        titles.addWidget(brand)
        titles.addWidget(label("Videos & playlists → MP4 / MP3", "tagline"))
        h.addLayout(titles)  # URL card is inserted after this (index 2)
        about = button("About && credits", "ghost")
        about.clicked.connect(lambda: AboutDialog(self).exec())
        h.addWidget(about)
        return h

    def _build_url_card(self):
        c = card()
        lay = QHBoxLayout(c)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)
        self.url_input = QLineEdit()
        self.url_input.setObjectName("urlInput")
        self.url_input.setPlaceholderText("Paste a YouTube video or playlist link…  (or drop links onto the window)")
        self.url_input.setClearButtonEnabled(True)
        self.url_input.returnPressed.connect(self.fetch)
        lay.addWidget(self.url_input, 1)
        paste = button("Paste", tip="Paste from clipboard and fetch")
        paste.clicked.connect(self._paste_and_fetch)
        lay.addWidget(paste)
        self.fetch_btn = button("Fetch  ➜", "primary")
        self.fetch_btn.setMinimumWidth(120)
        self.fetch_btn.clicked.connect(self.fetch)
        lay.addWidget(self.fetch_btn)
        return c

    def _build_hero_card(self):
        c = card()
        lay = QHBoxLayout(c)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(16)
        self.hero_img = QLabel()
        self.hero_img.setFixedSize(HERO_W, HERO_H)
        self.hero_img.setPixmap(placeholder_pix(HERO_W, HERO_H, 12))
        lay.addWidget(self.hero_img, 0, Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(6)
        self.hero_kind = label("NOTHING LOADED YET", "sectionTitle")
        self.hero_title = label("Paste a link to get started", "heroTitle")
        self.hero_title.setWordWrap(True)
        self.hero_sub = label("Single videos and public playlists are supported.", "muted")
        self.hero_sub.setWordWrap(True)
        self.hero_pills = QHBoxLayout()
        self.hero_pills.setSpacing(6)
        self.hero_pills.addStretch(1)
        self.status_lbl = label("", "muted")
        self.status_lbl.setWordWrap(True)
        info.addWidget(self.hero_kind)
        info.addWidget(self.hero_title)
        info.addWidget(self.hero_sub)
        info.addLayout(self.hero_pills)
        info.addStretch(1)
        info.addWidget(self.status_lbl)
        lay.addLayout(info, 1)
        return c

    def _build_options_card(self):
        c = card()
        g = QGridLayout(c)
        g.setContentsMargins(16, 14, 16, 14)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        g.addWidget(label("DEFAULT OUTPUT", "sectionTitle"), 0, 0, 1, 4)

        # mode segmented control
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.mode_video = button("🎬  Video")
        self.mode_audio = button("🎵  MP3")
        for b, pos in ((self.mode_video, "left"), (self.mode_audio, "right")):
            b.setObjectName("segment")
            b.setProperty("pos", pos)
            b.setCheckable(True)
            b.setMinimumWidth(118)
            seg.addWidget(b)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.mode_video)
        self.mode_group.addButton(self.mode_audio)
        self.mode_group.buttonClicked.connect(lambda _b: self._update_mode_widgets())
        segw = QWidget()
        segw.setLayout(seg)
        seg.setContentsMargins(0, 0, 0, 0)
        g.addWidget(label("Mode"), 1, 0)
        g.addWidget(segw, 1, 1)

        self.res_combo = QComboBox()
        self.res_combo.addItem("Best available", 0)
        for h in engine.VIDEO_HEIGHTS:
            self.res_combo.addItem(_height_label(h), h)
        self.container_combo = QComboBox()
        self.container_combo.addItem("MP4 (most compatible)", "mp4")
        self.container_combo.addItem("MKV", "mkv")
        self.bitrate_combo = QComboBox()
        for k in engine.AUDIO_BITRATES:
            self.bitrate_combo.addItem(f"{k} kbps", k)
        self.bitrate_combo.addItem("Best VBR (V0)", 0)

        self.res_lbl = label("Resolution")
        self.cont_lbl = label("Container")
        self.bit_lbl = label("MP3 bitrate")
        g.addWidget(self.res_lbl, 1, 2)
        g.addWidget(self.res_combo, 1, 3)
        g.addWidget(self.bit_lbl, 2, 2)
        g.addWidget(self.bitrate_combo, 2, 3)
        g.addWidget(self.cont_lbl, 2, 0)
        g.addWidget(self.container_combo, 2, 1)

        # destination
        g.addWidget(label("Save to"), 3, 0)
        dest = QHBoxLayout()
        self.dest_input = QLineEdit()
        dest.addWidget(self.dest_input, 1)
        browse = button("Browse…")
        browse.clicked.connect(self._browse)
        dest.addWidget(browse)
        openb = button("Open", tip="Open the destination folder")
        openb.clicked.connect(lambda: self._open_folder(self.dest_input.text()))
        dest.addWidget(openb)
        g.addLayout(dest, 3, 1, 1, 3)

        checks = QHBoxLayout()
        checks.setSpacing(16)
        self.chk_thumb = QCheckBox("Cover art")
        self.chk_meta = QCheckBox("Tags")
        self.chk_subdir = QCheckBox("Playlist folder")
        self.chk_number = QCheckBox("Number files")
        self.chk_subdir.setToolTip("Save playlist videos into a folder named after the playlist")
        self.chk_number.setToolTip("Prefix playlist files with their position, e.g. “007 - Title.mp3”")
        for w in (self.chk_thumb, self.chk_meta, self.chk_subdir, self.chk_number):
            checks.addWidget(w)
        checks.addStretch(1)
        checks.addWidget(label("Parallel"))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 6)
        self.parallel_spin.setToolTip("How many downloads run at the same time")
        self.parallel_spin.setFixedWidth(52)
        self.parallel_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        checks.addWidget(self.parallel_spin)
        g.addLayout(checks, 4, 0, 1, 4)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        return c

    def _build_list_card(self):
        c = card()
        v = QVBoxLayout(c)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.list_title = label("DOWNLOAD LIST", "sectionTitle")
        bar.addWidget(self.list_title)
        self.count_lbl = label("", "pill")
        bar.addWidget(self.count_lbl)
        bar.addSpacing(10)
        b_all = button("Check all")
        b_all.clicked.connect(lambda: self._check_all(True))
        b_none = button("Uncheck all")
        b_none.clicked.connect(lambda: self._check_all(False))
        bar.addWidget(b_all)
        bar.addWidget(b_none)
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("🔍  Filter by title…")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setMaximumWidth(240)
        self.filter_input.textChanged.connect(self._apply_filter)
        bar.addWidget(self.filter_input)
        bar.addStretch(1)
        apply_btn = button(
            "Apply default output to checked ⤵",
            tip="Set the format and quality chosen above on every checked row",
        )
        apply_btn.clicked.connect(self._apply_defaults_to_checked)
        bar.addWidget(apply_btn)
        clear = button("Clear finished", tip="Remove downloaded rows (hold Shift to remove all idle rows)")
        clear.clicked.connect(self._clear_rows)
        bar.addWidget(clear)
        v.addLayout(bar)

        self.stack = QStackedWidget()
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.addStretch(1)
        big = QLabel()
        big.setPixmap(QIcon(str(paths.asset("icon.svg"))).pixmap(72, 72))
        big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        big.setStyleSheet("opacity: 0.6;")
        el.addWidget(big)
        t = label("Your list is empty", "heroTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(t)
        s = label("Fetch a video or a playlist — every video shows up here so you can pick formats and download in bulk.", "muted")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setWordWrap(True)
        el.addWidget(s)
        el.addStretch(1)
        self.stack.addWidget(empty)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setDefaultSectionSize(THUMB_H + 14)
        self.table.setIconSize(QPixmap(THUMB_W, THUMB_H).size())
        hh = self.table.horizontalHeader()
        hh.setHighlightSections(False)
        for col, w in ((C_CHECK, 36), (C_THUMB, THUMB_W + 14), (C_IDX, 46), (C_DUR, 70), (C_MODE, 116), (C_QUAL, 112), (C_PROG, 210), (C_ACT, 80)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, w)
        hh.setSectionResizeMode(C_TITLE, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._item_changed)
        self.table.cellDoubleClicked.connect(self._row_double_clicked)
        self.stack.addWidget(self.table)
        v.addWidget(self.stack, 1)

        foot = QHBoxLayout()
        foot.setSpacing(10)
        prog_box = QVBoxLayout()
        prog_box.setSpacing(4)
        self.overall_lbl = label("Ready", "muted")
        self.overall = QProgressBar()
        self.overall.setObjectName("overall")
        self.overall.setTextVisible(False)
        self.overall.setRange(0, 1000)
        prog_box.addWidget(self.overall_lbl)
        prog_box.addWidget(self.overall)
        foot.addLayout(prog_box, 1)
        self.toggle_log_btn = button("Show log", "ghost")
        self.toggle_log_btn.clicked.connect(self._toggle_log)
        foot.addWidget(self.toggle_log_btn)
        self.cancel_btn = button("Cancel all", "danger")
        self.cancel_btn.clicked.connect(self.cancel_all)
        foot.addWidget(self.cancel_btn)
        self.download_btn = button("⬇  Download checked", "primary")
        self.download_btn.setMinimumWidth(220)
        self.download_btn.clicked.connect(self.start_downloads)
        foot.addWidget(self.download_btn)
        v.addLayout(foot)
        return c

    def _build_statusbar(self):
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        links = [
            ("yt-dlp", "https://github.com/yt-dlp/yt-dlp"),
            ("FFmpeg", "https://ffmpeg.org"),
            ("Deno", "https://deno.com"),
            ("Qt for Python", "https://doc.qt.io/qtforpython-6/"),
        ]
        credit = QLabel(
            "Powered by "
            + " · ".join(f'<a style="color:#9d86ff;text-decoration:none" href="{u}">{n}</a>' for n, u in links)
        )
        credit.setOpenExternalLinks(True)
        credit.setTextFormat(Qt.TextFormat.RichText)
        sb.addWidget(credit)
        self.tools_lbl = QLabel()
        sb.addPermanentWidget(self.tools_lbl)

    # ----------------------------------------------------------------- settings

    def _load_settings(self):
        s = self.settings
        default_dest = str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)) / "TubeSnatch")
        self.dest_input.setText(s.value("dest", default_dest))
        (self.mode_audio if s.value("mode", "audio") == "audio" else self.mode_video).setChecked(True)
        _select_data(self.res_combo, int(s.value("height", 1080)))
        _select_data(self.container_combo, s.value("container", "mp4"))
        _select_data(self.bitrate_combo, int(s.value("kbps", 320)))
        self.chk_thumb.setChecked(_bool(s.value("thumb", True)))
        self.chk_meta.setChecked(_bool(s.value("meta", True)))
        self.chk_subdir.setChecked(_bool(s.value("subdir", True)))
        self.chk_number.setChecked(_bool(s.value("number", True)))
        self.parallel_spin.setValue(int(s.value("parallel", 3)))
        geo = s.value("geometry")
        if geo:
            self.restoreGeometry(geo)

    def _save_settings(self):
        s = self.settings
        s.setValue("dest", self.dest_input.text())
        s.setValue("mode", self.default_mode())
        s.setValue("height", self.res_combo.currentData())
        s.setValue("container", self.container_combo.currentData())
        s.setValue("kbps", self.bitrate_combo.currentData())
        s.setValue("thumb", self.chk_thumb.isChecked())
        s.setValue("meta", self.chk_meta.isChecked())
        s.setValue("subdir", self.chk_subdir.isChecked())
        s.setValue("number", self.chk_number.isChecked())
        s.setValue("parallel", self.parallel_spin.value())
        s.setValue("geometry", self.saveGeometry())

    def _check_tools(self):
        bits = []
        bits.append("FFmpeg ✓" if paths.ffmpeg_dir() else "FFmpeg ✗")
        bits.append("Deno ✓" if paths.deno_path() else "Deno ✗")
        bits.append(f"yt-dlp {engine.ytdlp_version()}")
        bits.append(f"v{__version__}")
        self.tools_lbl.setText("   ".join(bits))
        if not paths.ffmpeg_dir():
            self._set_status("FFmpeg was not found — MP3 conversion and merging HD video will fail.", "error")

    # ----------------------------------------------------------------- defaults

    def default_mode(self) -> str:
        return "audio" if self.mode_audio.isChecked() else "video"

    def default_quality(self, mode: str) -> int:
        return self.bitrate_combo.currentData() if mode == "audio" else self.res_combo.currentData()

    def _update_mode_widgets(self):
        video = self.default_mode() == "video"
        for w in (self.res_combo, self.res_lbl, self.container_combo, self.cont_lbl):
            w.setEnabled(video)
        for w in (self.bitrate_combo, self.bit_lbl):
            w.setEnabled(not video)

    # ----------------------------------------------------------------- fetching

    def _paste_and_fetch(self):
        text = QApplication.clipboard().text().strip()
        if text:
            self.url_input.setText(text)
            self.fetch()

    def fetch(self, url: str | None = None):
        url = (url or self.url_input.text()).strip()
        if not url:
            self._set_status("Paste a link first.", "error")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self._probing += 1
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching…")
        self._set_status(f"Fetching info for {url} …")
        w = ProbeWorker(url)
        w.signals.done.connect(self._probe_done)
        w.signals.failed.connect(self._probe_failed)
        w.signals.log.connect(self.log)
        self.probe_pool.start(w)

    def _probe_finished(self):
        self._probing = max(0, self._probing - 1)
        if not self._probing:
            self.fetch_btn.setEnabled(True)
            self.fetch_btn.setText("Fetch  ➜")

    def _probe_failed(self, msg: str):
        self._probe_finished()
        self._set_status(f"Couldn't load that link: {msg}", "error")
        self.log(f"Fetch failed: {msg}")

    def _probe_done(self, res: engine.ProbeResult):
        self._probe_finished()
        self._show_hero(res)
        existing = {r.entry.id for r in self.rows if r.entry.id}
        added = 0
        mode = self.default_mode()
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        for e in res.entries:
            if e.id and e.id in existing:
                continue
            pl = res.title if res.kind == "playlist" else None
            q = _nearest_height(self.default_quality(mode), e.heights) if mode == "video" else self.default_quality(mode)
            row = Row(self._next_key, e, pl, mode, q)
            self._next_key += 1
            self.rows.append(row)
            self._add_table_row(row)
            added += 1
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.stack.setCurrentIndex(1 if self.rows else 0)
        skipped = len(res.entries) - added
        msg = f"Added {added} video{'s' if added != 1 else ''} to the list."
        if skipped:
            msg += f" ({skipped} already in the list)"
        self._set_status(msg, "ok")
        self.url_input.clear()
        self._refresh_counts()
        self._apply_filter()

    def _show_hero(self, res: engine.ProbeResult):
        self.hero_kind.setText("PLAYLIST" if res.kind == "playlist" else "VIDEO")
        self.hero_title.setText(res.title)
        self.hero_sub.setText(res.uploader or "")
        while self.hero_pills.count():
            item = self.hero_pills.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        pills = []
        if res.kind == "playlist":
            total = sum(e.duration or 0 for e in res.entries)
            pills += [f"{len(res.entries)} videos", f"⏱ {engine.fmt_duration(total)}"]
        else:
            e = res.entries[0]
            pills.append(f"⏱ {engine.fmt_duration(e.duration)}")
            if e.heights:
                pills.append(f"up to {_height_label(e.heights[0])}")
        for p in pills:
            self.hero_pills.addWidget(label(p, "pill"))
        self.hero_pills.addStretch(1)
        self.hero_img.setPixmap(placeholder_pix(HERO_W, HERO_H, 12))
        self.thumbs.get(res.thumbnail, lambda pix: self.hero_img.setPixmap(rounded(pix, HERO_W, HERO_H, 12)))

    # ----------------------------------------------------------------- table rows

    def _row_index(self, key: int) -> int:
        for i, r in enumerate(self.rows):
            if r.key == key:
                return i
        return -1

    def _add_table_row(self, row: Row):
        i = self.table.rowCount()
        self.table.insertRow(i)
        e = row.entry

        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        chk.setCheckState(Qt.CheckState.Checked)
        chk.setData(Qt.ItemDataRole.UserRole, row.key)
        self.table.setItem(i, C_CHECK, chk)

        thumb = QLabel()
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setPixmap(placeholder_pix(THUMB_W, THUMB_H, 8))
        self.table.setCellWidget(i, C_THUMB, thumb)
        self.thumbs.get(e.thumbnail, lambda pix, w=thumb: w.setPixmap(rounded(pix, THUMB_W, THUMB_H, 8)))

        idx = QTableWidgetItem(str(e.index) if row.playlist_title else "•")
        idx.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        idx.setForeground(QColor(theme.MUTED))
        self.table.setItem(i, C_IDX, idx)

        title = QTableWidgetItem(e.title + (f"\n{e.uploader}" if e.uploader else ""))
        title.setToolTip(f"{e.title}\n{e.url}\n\nDouble-click to open in your browser")
        f = QFont()
        f.setPointSizeF(10)
        title.setFont(f)
        self.table.setItem(i, C_TITLE, title)

        dur = QTableWidgetItem(engine.fmt_duration(e.duration))
        dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        dur.setForeground(QColor(theme.MUTED))
        self.table.setItem(i, C_DUR, dur)

        mode = QComboBox()
        mode.setObjectName("cellCombo")
        mode.addItem("🎬 Video", "video")
        mode.addItem("🎵 MP3", "audio")
        _select_data(mode, row.mode)
        mode.currentIndexChanged.connect(lambda _i, k=row.key: self._row_mode_changed(k))
        self.table.setCellWidget(i, C_MODE, _centered(mode))

        qual = QComboBox()
        qual.setObjectName("cellCombo")
        self.table.setCellWidget(i, C_QUAL, _centered(qual))
        self._fill_quality(row, qual)
        qual.currentIndexChanged.connect(lambda _i, k=row.key: self._row_quality_changed(k))

        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setValue(0)
        bar.setFormat("Ready")
        self.table.setCellWidget(i, C_PROG, _centered(bar))

        act = button("Open", "cellBtn", tip="Show the downloaded file")
        act.setEnabled(False)
        act.clicked.connect(lambda _c=False, k=row.key: self._row_action(k))
        self.table.setCellWidget(i, C_ACT, _centered(act))

    def _cell(self, i: int, col: int):
        w = self.table.cellWidget(i, col)
        return w.property("inner") if w is not None else None

    def _fill_quality(self, row: Row, combo: QComboBox):
        combo.blockSignals(True)
        combo.clear()
        if row.mode == "audio":
            for k in engine.AUDIO_BITRATES:
                combo.addItem(f"{k} kbps", k)
            combo.addItem("Best VBR", 0)
        else:
            combo.addItem("Best", 0)
            for h in row.entry.heights or engine.VIDEO_HEIGHTS:
                combo.addItem(f"{h}p", h)
        if not _select_data(combo, row.quality):
            combo.setCurrentIndex(0)
            row.quality = combo.currentData()
        combo.blockSignals(False)

    def _row_mode_changed(self, key: int):
        i = self._row_index(key)
        row = self.rows[i]
        row.mode = self._cell(i, C_MODE).currentData()
        row.quality = self.default_quality(row.mode)
        if row.mode == "video":
            row.quality = _nearest_height(row.quality, row.entry.heights)
        self._fill_quality(row, self._cell(i, C_QUAL))

    def _row_quality_changed(self, key: int):
        i = self._row_index(key)
        self.rows[i].quality = self._cell(i, C_QUAL).currentData()

    def _apply_defaults_to_checked(self):
        mode = self.default_mode()
        n = 0
        for i, row in enumerate(self.rows):
            if not self._is_checked(i) or row.state in ("queued", "running"):
                continue
            row.mode = mode
            q = self.default_quality(mode)
            row.quality = _nearest_height(q, row.entry.heights) if mode == "video" else q
            mcombo = self._cell(i, C_MODE)
            mcombo.blockSignals(True)
            _select_data(mcombo, mode)
            mcombo.blockSignals(False)
            self._fill_quality(row, self._cell(i, C_QUAL))
            n += 1
        what = "MP3 " + self.bitrate_combo.currentText() if mode == "audio" else "Video " + self.res_combo.currentText()
        self._set_status(f"Applied “{what}” to {n} checked row{'s' if n != 1 else ''}.", "ok")

    def _is_checked(self, i: int) -> bool:
        it = self.table.item(i, C_CHECK)
        return bool(it and it.checkState() == Qt.CheckState.Checked)

    def _check_all(self, on: bool):
        self.table.blockSignals(True)
        for i in range(self.table.rowCount()):
            if not self.table.isRowHidden(i):
                self.table.item(i, C_CHECK).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._refresh_counts()

    def _item_changed(self, item: QTableWidgetItem):
        if item.column() == C_CHECK:
            self._refresh_counts()

    def _apply_filter(self):
        q = self.filter_input.text().strip().lower()
        for i, row in enumerate(self.rows):
            hay = f"{row.entry.title} {row.entry.uploader}".lower()
            self.table.setRowHidden(i, bool(q) and q not in hay)

    def _row_double_clicked(self, i: int, col: int):
        if col in (C_TITLE, C_THUMB, C_IDX) and 0 <= i < len(self.rows):
            QDesktopServices.openUrl(QUrl(self.rows[i].entry.url))

    def _row_action(self, key: int):
        i = self._row_index(key)
        if i >= 0 and self.rows[i].path:
            _reveal(self.rows[i].path)

    def _clear_rows(self):
        shift = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        drop = {"done"} | ({"idle", "error", "cancelled"} if shift else set())
        for i in range(len(self.rows) - 1, -1, -1):
            if self.rows[i].state in drop:
                self.table.removeRow(i)
                del self.rows[i]
        self.stack.setCurrentIndex(1 if self.rows else 0)
        self._refresh_counts()

    # ----------------------------------------------------------------- downloading

    def _job_options(self, row: Row) -> engine.JobOptions:
        base = self.dest_input.text().strip() or "."
        outdir = base
        prefix = ""
        if row.playlist_title:
            if self.chk_subdir.isChecked():
                outdir = engine.playlist_folder(base, row.playlist_title)
            if self.chk_number.isChecked():
                prefix = f"{row.entry.index:03d} - "
        return engine.JobOptions(
            outdir=outdir,
            mode=row.mode,
            height=row.quality if row.mode == "video" else 0,
            container=self.container_combo.currentData(),
            audio_kbps=row.quality if row.mode == "audio" else 320,
            embed_thumbnail=self.chk_thumb.isChecked(),
            embed_metadata=self.chk_meta.isChecked(),
            filename_prefix=prefix,
        )

    def start_downloads(self):
        dest = self.dest_input.text().strip()
        if not dest:
            self._set_status("Choose a destination folder first.", "error")
            return
        try:
            Path(dest).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self._set_status(f"Can't use that folder: {e}", "error")
            return
        self.dl_pool.setMaxThreadCount(self.parallel_spin.value())
        started = 0
        for i, row in enumerate(self.rows):
            if not self._is_checked(i) or row.state in ("queued", "running", "done"):
                continue
            w = DownloadWorker(row.key, row.entry.url, self._job_options(row))
            w.signals.progress.connect(self._on_progress)
            w.signals.finished.connect(self._on_finished)
            w.signals.failed.connect(self._on_failed)
            w.signals.log.connect(self.log)
            row.worker = w
            row.state = "queued"
            self._set_row_ui(i, 0, "Queued", "")
            self._lock_row(i, True)
            self.dl_pool.start(w)
            started += 1
        if started:
            self._set_status(f"Started {started} download{'s' if started != 1 else ''} → {dest}", "ok")
        else:
            self._set_status("Nothing to download — check some rows that aren't finished yet.", "error")
        self._refresh_counts()

    def cancel_all(self):
        n = 0
        for i, row in enumerate(self.rows):
            if row.state in ("queued", "running") and row.worker:
                row.worker.cancel.set()
                if row.state == "queued" and self.dl_pool.tryTake(row.worker):
                    self._on_failed(row.key, "Cancelled")
                n += 1
        if n:
            self._set_status(f"Cancelling {n} download{'s' if n != 1 else ''}…")

    def _on_progress(self, key: int, p: engine.Progress):
        i = self._row_index(key)
        if i < 0:
            return
        row = self.rows[i]
        if row.state == "queued":
            row.state = "running"
        bar = self._cell(i, C_PROG)
        if p.fraction is not None:
            bar.setValue(int(p.fraction * 1000))
        bar.setFormat(p.text)
        bar.setToolTip(p.text)
        self._refresh_counts()

    def _on_finished(self, key: int, path: str):
        i = self._row_index(key)
        if i < 0:
            return
        row = self.rows[i]
        row.state, row.path, row.worker = "done", path, None
        self._set_row_ui(i, 1000, "✓ Saved", "done", tip=path)
        self._cell(i, C_ACT).setEnabled(bool(path))
        self._lock_row(i, False)
        self.table.item(i, C_CHECK).setCheckState(Qt.CheckState.Unchecked)
        self.log(f"Saved: {path}")
        self._refresh_counts()

    def _on_failed(self, key: int, msg: str):
        i = self._row_index(key)
        if i < 0:
            return
        row = self.rows[i]
        cancelled = msg == "Cancelled"
        row.state = "cancelled" if cancelled else "error"
        row.worker = None
        self._set_row_ui(i, 1000 if not cancelled else 0, "Cancelled" if cancelled else f"✕ {msg}", "error", tip=msg)
        self._lock_row(i, False)
        if not cancelled:
            self.log(f"Failed: {row.entry.title} — {msg}")
        self._refresh_counts()

    def _set_row_ui(self, i: int, value: int, text: str, state: str, tip: str = ""):
        bar = self._cell(i, C_PROG)
        bar.setValue(value)
        bar.setFormat(text.replace("%", "%%"))
        bar.setToolTip(tip or text)
        bar.setProperty("state", state)
        bar.style().unpolish(bar)
        bar.style().polish(bar)

    def _lock_row(self, i: int, locked: bool):
        self._cell(i, C_MODE).setEnabled(not locked)
        self._cell(i, C_QUAL).setEnabled(not locked)

    def _refresh_counts(self):
        total = len(self.rows)
        checked = sum(1 for i in range(total) if self._is_checked(i))
        self.count_lbl.setText(f"{checked} of {total} checked" if total else "empty")
        states = [r.state for r in self.rows]
        active = [r for r in self.rows if r.state in ("queued", "running")]
        done = states.count("done")
        failed = states.count("error")
        self.cancel_btn.setEnabled(bool(active))
        self.download_btn.setEnabled(checked > 0)
        self.download_btn.setText(f"⬇  Download checked ({checked})" if checked else "⬇  Download checked")
        batch = [r for r in self.rows if r.state in ("queued", "running", "done", "error", "cancelled")]
        if active:
            frac = 0.0
            for r in batch:
                if r.state in ("done", "error", "cancelled"):
                    frac += 1
                elif r.state == "running":
                    frac += self._cell(self._row_index(r.key), C_PROG).value() / 1000
            self.overall.setValue(int(frac / max(1, len(batch)) * 1000))
            self.overall_lbl.setText(
                f"Downloading… {done} done · {len(active)} in progress" + (f" · {failed} failed" if failed else "")
            )
        else:
            self.overall.setValue(1000 if batch else 0)
            if batch:
                self.overall_lbl.setText(f"Finished — {done} saved" + (f", {failed} failed (check them and retry)" if failed else ""))
            else:
                self.overall_lbl.setText("Ready")

    # ----------------------------------------------------------------- misc

    def log(self, msg: str):
        self.log_view.appendPlainText(msg.rstrip())

    def _toggle_log(self):
        vis = not self.log_view.isVisible()
        self.log_view.setVisible(vis)
        self.toggle_log_btn.setText("Hide log" if vis else "Show log")

    def _set_status(self, text: str, kind: str = "muted"):
        self.status_lbl.setObjectName({"error": "error", "ok": "ok"}.get(kind, "muted"))
        self.status_lbl.setText(text)
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose destination folder", self.dest_input.text())
        if d:
            self.dest_input.setText(d)

    def _open_folder(self, path: str):
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        urls = [u.toString() for u in md.urls()] if md.hasUrls() else md.text().split()
        for i, u in enumerate(u for u in urls if u.startswith("http")):
            QTimer.singleShot(i * 150, lambda u=u: self.fetch(u))

    def closeEvent(self, e):
        active = [r for r in self.rows if r.state in ("queued", "running")]
        if active:
            ans = QMessageBox.question(
                self, "Downloads in progress", f"{len(active)} download(s) are still running. Cancel them and quit?"
            )
            if ans != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            self.cancel_all()
            self.dl_pool.waitForDone(4000)
        self._save_settings()
        e.accept()


# --------------------------------------------------------------------------- helpers


def _centered(w: QWidget) -> QWidget:
    holder = QWidget()
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(6, 0, 6, 0)
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    lay.addWidget(w)
    holder.setProperty("inner", w)
    return holder


def _select_data(combo: QComboBox, value) -> bool:
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            combo.setCurrentIndex(i)
            return True
    return False


def _height_label(h: int) -> str:
    tag = {2160: " 4K", 1440: " 2K", 1080: " FHD", 720: " HD"}.get(h, "")
    return f"{h}p{tag}"


def _nearest_height(target: int, available: list[int]) -> int:
    if not target or not available:
        return target
    lower = [h for h in available if h <= target]
    return max(lower) if lower else min(available)


def _bool(v) -> bool:
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")


def _reveal(path: str):
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
