"""Download tab: URL bar, preview card, default output, download list."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import engine, paths
from ..archive import Archive
from . import theme
from .config import Config
from .row_dialog import RowOptionsDialog
from .widgets import (
    ThumbLoader,
    button,
    card,
    centered,
    height_label,
    label,
    nearest_height,
    open_folder,
    placeholder_pix,
    repolish,
    reveal,
    rounded,
    select_data,
)
from .workers import DownloadWorker, ProbeWorker

THUMB_W, THUMB_H = 96, 54
HERO_W, HERO_H = 208, 117

C_CHECK, C_THUMB, C_IDX, C_TITLE, C_DUR, C_FMT, C_QUAL, C_PROG, C_ACT = range(9)
HEADERS = ["", "", "#", "TITLE", "LENGTH", "FORMAT", "QUALITY", "PROGRESS", ""]

ACTIVE = ("queued", "running")


@dataclass
class Row:
    key: int
    entry: engine.Entry
    playlist_title: str | None
    fmt: str
    quality: int
    trim: tuple[float, float | None] | None = None
    split: bool | None = None  # None = follow the "Split chapters" default
    state: str = "idle"  # idle | queued | running | done | error | cancelled | archived
    path: str = ""
    worker: DownloadWorker | None = None


def fmt_item_label(fmt: str) -> str:
    return ("🎵 " if engine.is_audio(fmt) else "🎬 ") + engine.FORMAT_LABELS[fmt].split(" ")[0]


def fill_quality(combo: QComboBox, fmt: str, heights: list[int] | None, current: int, short: bool) -> int:
    """Populate a quality combo for ``fmt``; returns the selected value."""
    combo.blockSignals(True)
    combo.clear()
    if engine.is_audio(fmt):
        if fmt in engine.LOSSLESS:
            combo.addItem("Lossless", 0)
        else:
            for k in engine.AUDIO_BITRATES:
                combo.addItem(f"{k} kbps", k)
            combo.addItem("Best VBR" if fmt == "mp3" else "Best", 0)
    else:
        combo.addItem("Best" if short else "Best available", 0)
        for h in heights or engine.VIDEO_HEIGHTS:
            combo.addItem(f"{h}p" if short else height_label(h), h)
    if not select_data(combo, current):
        if not engine.is_audio(fmt) and heights:
            select_data(combo, nearest_height(current, heights))
        else:
            combo.setCurrentIndex(0)
    combo.blockSignals(False)
    return combo.currentData()


class DownloadTab(QWidget):
    log = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.cfg = config
        self.archive = Archive(Config.data_dir() / "download-archive.txt")
        self.thumbs = ThumbLoader(self)
        self.probe_pool = QThreadPool(self)
        self.probe_pool.setMaxThreadCount(2)
        self.dl_pool = QThreadPool(self)
        self.rows: list[Row] = []
        self._next_key = 1
        self._probing = 0
        self.restart_guard = None  # callable() -> bool; False blocks new work (pending engine restart)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(self._build_url_card())
        mid = QHBoxLayout()
        mid.setSpacing(14)
        mid.addWidget(self._build_hero_card(), 2)
        mid.addWidget(self._build_options_card(), 3)
        root.addLayout(mid)
        root.addWidget(self._build_list_card(), 1)

        self._load_settings()
        self._refresh_counts()

    # ----------------------------------------------------------------- layout

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
        self.hero_title = label("Paste a link to get started", "heroTitle", wrap=True)
        self.hero_sub = label("Single videos and public playlists are supported.", "muted", wrap=True)
        self.hero_pills = QHBoxLayout()
        self.hero_pills.setSpacing(6)
        self.hero_pills.addStretch(1)
        self.status_lbl = label("", "muted")  # lives in the list footer (see _build_list_card)
        for w in (self.hero_kind, self.hero_title, self.hero_sub):
            info.addWidget(w)
        info.addLayout(self.hero_pills)
        info.addStretch(1)
        lay.addLayout(info, 1)
        return c

    def _build_options_card(self):
        c = card()
        g = QGridLayout(c)
        g.setContentsMargins(16, 14, 16, 14)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        g.addWidget(label("DEFAULT OUTPUT", "sectionTitle"), 0, 0, 1, 4)

        seg = QHBoxLayout()
        seg.setSpacing(0)
        seg.setContentsMargins(0, 0, 0, 0)
        self.mode_video = button("🎬  Video")
        self.mode_audio = button("🎵  Audio")
        for b, pos in ((self.mode_video, "left"), (self.mode_audio, "right")):
            b.setObjectName("segment")
            b.setProperty("pos", pos)
            b.setCheckable(True)
            b.setMinimumWidth(110)
            seg.addWidget(b)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.mode_video)
        self.mode_group.addButton(self.mode_audio)
        self.mode_group.buttonClicked.connect(lambda _b: self._mode_changed())
        segw = QWidget()
        segw.setLayout(seg)
        g.addWidget(label("Mode"), 1, 0)
        g.addWidget(segw, 1, 1)

        self.fmt_combo = QComboBox()
        self.fmt_combo.currentIndexChanged.connect(lambda _i: self._fmt_changed())
        g.addWidget(label("Format"), 1, 2)
        g.addWidget(self.fmt_combo, 1, 3)

        self.qual_combo = QComboBox()
        self.qual_combo.currentIndexChanged.connect(lambda _i: self._quality_changed())
        self.qual_lbl = label("Resolution")
        g.addWidget(self.qual_lbl, 2, 0)
        g.addWidget(self.qual_combo, 2, 1)

        g.addWidget(label("Parallel"), 2, 2)
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 6)
        self.parallel_spin.setToolTip("How many downloads run at the same time")
        self.parallel_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.parallel_spin.valueChanged.connect(lambda v: self.cfg.set("parallel", v))
        g.addWidget(self.parallel_spin, 2, 3)

        g.addWidget(label("Save to"), 3, 0)
        dest = QHBoxLayout()
        self.dest_input = QLineEdit()
        self.dest_input.editingFinished.connect(lambda: self.cfg.set("dest", self.dest_input.text()))
        dest.addWidget(self.dest_input, 1)
        browse = button("Browse…")
        browse.clicked.connect(self._browse)
        dest.addWidget(browse)
        openb = button("Open", tip="Open the destination folder")
        openb.clicked.connect(lambda: open_folder(self.dest_input.text()))
        dest.addWidget(openb)
        g.addLayout(dest, 3, 1, 1, 3)

        checks = QHBoxLayout()
        checks.setSpacing(16)
        self.chk_thumb = QCheckBox("Cover art")
        self.chk_meta = QCheckBox("Tags")
        self.chk_skip = QCheckBox("Skip downloaded")
        self.chk_skip.setToolTip("Videos you already downloaded with TubeSnatch start unchecked —\n"
                                 "re-fetch a playlist to grab only the new ones.")
        self.chk_split = QCheckBox("Split chapters")
        self.chk_split.setToolTip("One file per chapter (albums, mixes). Per-video override: the ✂ button.")
        for w, key in ((self.chk_thumb, "thumb"), (self.chk_meta, "meta"), (self.chk_skip, "skip_downloaded"),
                       (self.chk_split, "split_chapters")):
            w.toggled.connect(lambda on, k=key: self.cfg.set(k, on))
            checks.addWidget(w)
        self.chk_skip.toggled.connect(lambda _on: self._apply_skip())
        checks.addStretch(1)
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
        bar.addWidget(label("DOWNLOAD LIST", "sectionTitle"))
        self.count_lbl = label("", "pill")
        self.count_lbl.setMinimumWidth(118)
        self.count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        self.filter_input.setMaximumWidth(220)
        self.filter_input.textChanged.connect(self._apply_filter)
        bar.addWidget(self.filter_input)
        bar.addStretch(1)
        apply_btn = button("Apply default output to checked ⤵",
                           tip="Set the format and quality chosen above on every checked row")
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
        el.addWidget(big)
        t = label("Your list is empty", "heroTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(t)
        s = label("Fetch a video or a playlist — every video shows up here so you can pick formats, trim, "
                  "and download in bulk.", "muted", wrap=True)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        for col, w in ((C_CHECK, 36), (C_THUMB, THUMB_W + 14), (C_IDX, 46), (C_DUR, 70), (C_FMT, 112),
                       (C_QUAL, 124), (C_PROG, 200), (C_ACT, 104)):
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
        status_row = QHBoxLayout()
        status_row.addWidget(self.overall_lbl)
        status_row.addSpacing(12)
        status_row.addWidget(self.status_lbl, 1)
        self.status_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        prog_box.addLayout(status_row)
        prog_box.addWidget(self.overall)
        foot.addLayout(prog_box, 1)
        self.cancel_btn = button("Cancel all", "danger")
        self.cancel_btn.clicked.connect(self.cancel_all)
        foot.addWidget(self.cancel_btn)
        self.download_btn = button("⬇  Download checked", "primary")
        self.download_btn.setMinimumWidth(220)
        self.download_btn.clicked.connect(self.start_downloads)
        foot.addWidget(self.download_btn)
        v.addLayout(foot)
        return c

    # ----------------------------------------------------------------- settings / defaults

    def _load_settings(self):
        c = self.cfg
        self.dest_input.setText(c.get("dest") or Config.default_dest())
        (self.mode_audio if c.get("mode") == "audio" else self.mode_video).setChecked(True)
        self.chk_thumb.setChecked(c.get("thumb"))
        self.chk_meta.setChecked(c.get("meta"))
        self.chk_skip.setChecked(c.get("skip_downloaded"))
        self.chk_split.setChecked(c.get("split_chapters"))
        self.parallel_spin.setValue(c.get("parallel"))
        self._mode_changed(save=False)

    def save_settings(self):
        self.cfg.set("dest", self.dest_input.text())

    def default_mode(self) -> str:
        return "audio" if self.mode_audio.isChecked() else "video"

    def default_fmt(self) -> str:
        return self.fmt_combo.currentData()

    def default_quality(self) -> int:
        return self.qual_combo.currentData()

    def _mode_changed(self, save: bool = True):
        mode = self.default_mode()
        if save:
            self.cfg.set("mode", mode)
        fmts = engine.AUDIO_FORMATS if mode == "audio" else engine.VIDEO_FORMATS
        self.fmt_combo.blockSignals(True)
        self.fmt_combo.clear()
        for f in fmts:
            self.fmt_combo.addItem(engine.FORMAT_LABELS[f], f)
        select_data(self.fmt_combo, self.cfg.get("audio_fmt" if mode == "audio" else "video_fmt"))
        self.fmt_combo.blockSignals(False)
        self._fmt_changed()

    def _fmt_changed(self):
        fmt = self.default_fmt()
        if fmt is None:
            return
        audio = engine.is_audio(fmt)
        self.cfg.set("audio_fmt" if audio else "video_fmt", fmt)
        self.qual_lbl.setText("Bitrate" if audio else "Resolution")
        fill_quality(self.qual_combo, fmt, None, self.cfg.get("kbps" if audio else "height"), short=False)
        self.qual_combo.setEnabled(fmt not in engine.LOSSLESS)

    def _quality_changed(self):
        fmt = self.default_fmt()
        if fmt and fmt not in engine.LOSSLESS:
            self.cfg.set("kbps" if engine.is_audio(fmt) else "height", self.default_quality())

    # ----------------------------------------------------------------- fetching

    def _guard(self) -> bool:
        return self.restart_guard() if self.restart_guard else True

    def _paste_and_fetch(self):
        text = QApplication.clipboard().text().strip()
        if text:
            self.url_input.setText(text)
            self.fetch()

    def fetch(self, url: str | None = None):
        url = (url if isinstance(url, str) and url else self.url_input.text()).strip()
        if not url:
            self.set_status("Paste a link first.", "error")
            return
        if not self._guard():
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self._probing += 1
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching…")
        self.set_status(f"Fetching info for {url} …")
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
        self.set_status(f"Couldn't load that link: {msg}", "error")
        self.log.emit(f"Fetch failed: {msg}")

    def _probe_done(self, res: engine.ProbeResult):
        self._probe_finished()
        self._show_hero(res)
        existing = {r.entry.id for r in self.rows if r.entry.id}
        added = archived = 0
        fmt, q = self.default_fmt(), self.default_quality()
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        for e in res.entries:
            if e.id and e.id in existing:
                continue
            pl = res.title if res.kind == "playlist" else None
            rq = nearest_height(q, e.heights) if not engine.is_audio(fmt) else q
            row = Row(self._next_key, e, pl, fmt, rq)
            if e.archive_key in self.archive:
                row.state = "archived"
                archived += 1
            self._next_key += 1
            self.rows.append(row)
            self._add_table_row(row)
            added += 1
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.stack.setCurrentIndex(1 if self.rows else 0)
        skipped = len(res.entries) - added
        msg = f"Added {added} video{'s' if added != 1 else ''}."
        if archived:
            msg += f" {archived} downloaded before" + (" (unchecked)." if self.chk_skip.isChecked() else ".")
        if skipped:
            msg += f" {skipped} already in the list."
        self.set_status(msg, "ok")
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
            new = sum(1 for e in res.entries if e.archive_key not in self.archive)
            if new != len(res.entries):
                pills.append(f"{new} new")
        else:
            e = res.entries[0]
            pills.append(f"⏱ {engine.fmt_duration(e.duration)}")
            if e.heights:
                pills.append(f"up to {height_label(e.heights[0])}")
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

    def _cell(self, i: int, col: int):
        w = self.table.cellWidget(i, col)
        return w.property("inner") if w is not None else None

    def _add_table_row(self, row: Row):
        i = self.table.rowCount()
        self.table.insertRow(i)
        e = row.entry

        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        skip = row.state == "archived" and self.chk_skip.isChecked()
        chk.setCheckState(Qt.CheckState.Unchecked if skip else Qt.CheckState.Checked)
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

        title = QTableWidgetItem()
        f = QFont()
        f.setPointSizeF(10)
        title.setFont(f)
        self.table.setItem(i, C_TITLE, title)
        self._update_title(i)

        dur = QTableWidgetItem(engine.fmt_duration(e.duration))
        dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        dur.setForeground(QColor(theme.MUTED))
        self.table.setItem(i, C_DUR, dur)

        fmt = QComboBox()
        fmt.setObjectName("cellCombo")
        for fm in engine.VIDEO_FORMATS + engine.AUDIO_FORMATS:
            fmt.addItem(fmt_item_label(fm), fm)
        select_data(fmt, row.fmt)
        fmt.currentIndexChanged.connect(lambda _i, k=row.key: self._row_fmt_changed(k))
        self.table.setCellWidget(i, C_FMT, centered(fmt))

        qual = QComboBox()
        qual.setObjectName("cellCombo")
        self.table.setCellWidget(i, C_QUAL, centered(qual))
        row.quality = fill_quality(qual, row.fmt, e.heights, row.quality, short=True)
        qual.currentIndexChanged.connect(lambda _i, k=row.key: self._row_quality_changed(k))

        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setValue(0)
        bar.setFormat("Ready")
        self.table.setCellWidget(i, C_PROG, centered(bar))
        if row.state == "archived":
            self._set_row_ui(i, 0, "✓ Downloaded before", "", tip="Already in your download history")

        acts = QWidget()
        al = QHBoxLayout(acts)
        al.setContentsMargins(4, 0, 4, 0)
        al.setSpacing(4)
        opt = button("✂", "cellBtn", tip="Trim or split by chapters")
        opt.clicked.connect(lambda _c=False, k=row.key: self._row_options(k))
        opn = button("Open", "cellBtn", tip="Show the downloaded file")
        opn.setEnabled(False)
        opn.clicked.connect(lambda _c=False, k=row.key: self._row_open(k))
        al.addWidget(opt)
        al.addWidget(opn)
        acts.setProperty("inner", acts)
        acts.setProperty("opt", opt)
        acts.setProperty("open", opn)
        self.table.setCellWidget(i, C_ACT, acts)

    def _update_title(self, i: int):
        row = self.rows[i]
        e = row.entry
        lines = [e.title]
        sub = e.uploader
        if row.trim:
            s, en = row.trim
            tag = f"✂ {engine.fmt_duration(s)}–{engine.fmt_duration(en) if en is not None else 'end'}"
            sub = f"{tag}   {sub}" if sub else tag
        elif row.split:
            sub = f"📑 split by chapters   {sub}" if sub else "📑 split by chapters"
        if sub:
            lines.append(sub)
        item = self.table.item(i, C_TITLE)
        item.setText("\n".join(lines))
        item.setToolTip(f"{e.title}\n{e.url}\n\nDouble-click to open in your browser")

    def _row_fmt_changed(self, key: int):
        i = self._row_index(key)
        row = self.rows[i]
        new = self._cell(i, C_FMT).currentData()
        switching = engine.is_audio(new) != engine.is_audio(row.fmt)
        row.fmt = new
        if switching:  # carry over the matching default quality
            row.quality = self.cfg.get("kbps" if engine.is_audio(new) else "height")
        row.quality = fill_quality(self._cell(i, C_QUAL), new, row.entry.heights, row.quality, short=True)
        self._cell(i, C_QUAL).setEnabled(new not in engine.LOSSLESS and row.state not in ACTIVE)

    def _row_quality_changed(self, key: int):
        i = self._row_index(key)
        self.rows[i].quality = self._cell(i, C_QUAL).currentData()

    def _row_options(self, key: int):
        i = self._row_index(key)
        row = self.rows[i]
        split = row.split if row.split is not None else self.chk_split.isChecked()
        dlg = RowOptionsDialog(self, row.entry.title, row.entry.duration, row.trim, split and not row.trim)
        if dlg.exec():
            row.trim, split = dlg.result_value
            row.split = split
            self._update_title(i)

    def _row_open(self, key: int):
        i = self._row_index(key)
        if i >= 0 and self.rows[i].path:
            reveal(self.rows[i].path)

    def _apply_defaults_to_checked(self):
        fmt, q = self.default_fmt(), self.default_quality()
        n = 0
        for i, row in enumerate(self.rows):
            if not self._is_checked(i) or row.state in ACTIVE:
                continue
            row.fmt = fmt
            row.quality = nearest_height(q, row.entry.heights) if not engine.is_audio(fmt) else q
            c = self._cell(i, C_FMT)
            c.blockSignals(True)
            select_data(c, fmt)
            c.blockSignals(False)
            row.quality = fill_quality(self._cell(i, C_QUAL), fmt, row.entry.heights, row.quality, short=True)
            self._cell(i, C_QUAL).setEnabled(fmt not in engine.LOSSLESS)
            n += 1
        what = f"{engine.FORMAT_LABELS[fmt]} · {self.qual_combo.currentText()}"
        self.set_status(f"Applied “{what}” to {n} checked row{'s' if n != 1 else ''}.", "ok")

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

    def _apply_skip(self):
        on = self.chk_skip.isChecked()
        self.table.blockSignals(True)
        for i, row in enumerate(self.rows):
            if row.state == "archived":
                self.table.item(i, C_CHECK).setCheckState(Qt.CheckState.Unchecked if on else Qt.CheckState.Checked)
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

    def _clear_rows(self):
        shift = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        drop = {"done"} | ({"idle", "error", "cancelled", "archived"} if shift else set())
        for i in range(len(self.rows) - 1, -1, -1):
            if self.rows[i].state in drop:
                self.table.removeRow(i)
                del self.rows[i]
        self.stack.setCurrentIndex(1 if self.rows else 0)
        self._refresh_counts()

    # ----------------------------------------------------------------- downloading

    def _job_options(self, row: Row) -> engine.JobOptions:
        base = self.dest_input.text().strip() or "."
        outdir, prefix = base, ""
        if row.playlist_title:
            if self.cfg.get("subdir"):
                outdir = engine.playlist_folder(base, row.playlist_title)
            if self.cfg.get("number"):
                prefix = f"{row.entry.index:03d} - "
        split = row.split if row.split is not None else self.chk_split.isChecked()
        return engine.JobOptions(
            outdir=outdir,
            fmt=row.fmt,
            quality=row.quality or 0,
            embed_thumbnail=self.chk_thumb.isChecked(),
            embed_metadata=self.chk_meta.isChecked(),
            filename_prefix=prefix,
            trim=row.trim,
            accurate_cuts=self.cfg.get("accurate_cuts"),
            split_chapters=bool(split) and not row.trim,
            subtitles=self.cfg.get("subtitles"),
            sub_langs=self.cfg.get("sub_langs"),
            sponsorblock=self.cfg.get("sponsorblock"),
            rate_limit=self.cfg.get("rate_limit"),
            normalize=self.cfg.get("normalize"),
        )

    def active_count(self) -> int:
        return sum(1 for r in self.rows if r.state in ACTIVE)

    def start_downloads(self):
        if not self._guard():
            return
        dest = self.dest_input.text().strip()
        if not dest:
            self.set_status("Choose a destination folder first.", "error")
            return
        try:
            Path(dest).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.set_status(f"Can't use that folder: {e}", "error")
            return
        self.cfg.set("dest", dest)
        self.dl_pool.setMaxThreadCount(self.parallel_spin.value())
        started = 0
        for i, row in enumerate(self.rows):
            if not self._is_checked(i) or row.state in ACTIVE or row.state == "done":
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
            self.set_status(f"Started {started} download{'s' if started != 1 else ''} → {dest}", "ok")
            self.busy_changed.emit(True)
        else:
            self.set_status("Nothing to download — check some rows that aren't finished yet.", "error")
        self._refresh_counts()

    def cancel_all(self):
        n = 0
        for row in self.rows:
            if row.state in ACTIVE and row.worker:
                row.worker.cancel.set()
                if row.state == "queued" and self.dl_pool.tryTake(row.worker):
                    self._on_failed(row.key, "Cancelled")
                n += 1
        if n:
            self.set_status(f"Cancelling {n} download{'s' if n != 1 else ''}…")

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

    def _on_finished(self, key: int, res: engine.DownloadResult):
        i = self._row_index(key)
        if i < 0:
            return
        row = self.rows[i]
        row.state, row.path, row.worker = "done", res.path, None
        n = len(res.files)
        self._set_row_ui(i, 1000, f"✓ Saved {n} files" if n > 1 else "✓ Saved", "done", tip=res.path)
        self._cell(i, C_ACT).property("open").setEnabled(bool(res.path))
        self._lock_row(i, False)
        self.table.item(i, C_CHECK).setCheckState(Qt.CheckState.Unchecked)
        if not row.trim:  # a clip doesn't count as "downloaded"
            self.archive.add(row.entry.archive_key)
        self.log.emit(f"Saved: {res.path}")
        self._refresh_counts()

    def _on_failed(self, key: int, msg: str):
        i = self._row_index(key)
        if i < 0:
            return
        row = self.rows[i]
        cancelled = msg == "Cancelled"
        row.state = "cancelled" if cancelled else "error"
        row.worker = None
        self._set_row_ui(i, 0 if cancelled else 1000, "Cancelled" if cancelled else f"✕ {msg}", "error", tip=msg)
        self._lock_row(i, False)
        if not cancelled:
            self.log.emit(f"Failed: {row.entry.title} — {msg}")
        self._refresh_counts()

    def _set_row_ui(self, i: int, value: int, text: str, state: str, tip: str = ""):
        bar = self._cell(i, C_PROG)
        bar.setValue(value)
        bar.setFormat(text)
        bar.setToolTip(tip or text)
        bar.setProperty("state", state)
        repolish(bar)

    def _lock_row(self, i: int, locked: bool):
        self._cell(i, C_FMT).setEnabled(not locked)
        self._cell(i, C_QUAL).setEnabled(not locked and self.rows[i].fmt not in engine.LOSSLESS)
        self._cell(i, C_ACT).property("opt").setEnabled(not locked)

    def _refresh_counts(self):
        total = len(self.rows)
        checked = sum(1 for i in range(total) if self._is_checked(i))
        self.count_lbl.setText(f"{checked}/{total} checked" if total else "empty")
        states = [r.state for r in self.rows]
        active = [r for r in self.rows if r.state in ACTIVE]
        done, failed = states.count("done"), states.count("error")
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
                f"Downloading… {done} done · {len(active)} in progress" + (f" · {failed} failed" if failed else ""))
        else:
            self.overall.setValue(1000 if batch else 0)
            if batch:
                self.overall_lbl.setText(
                    f"Finished — {done} saved" + (f", {failed} failed (check them and retry)" if failed else ""))
                self.busy_changed.emit(False)
            else:
                self.overall_lbl.setText("Ready")

    # ----------------------------------------------------------------- misc

    def set_status(self, text: str, kind: str = "muted"):
        self.status_lbl.setObjectName({"error": "error", "ok": "ok"}.get(kind, "muted"))
        full = text
        if len(text) > 140:
            text = text[:137] + "…"
        self.status_lbl.setText(text)
        self.status_lbl.setToolTip(full)
        repolish(self.status_lbl)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose destination folder", self.dest_input.text())
        if d:
            self.dest_input.setText(d)
            self.cfg.set("dest", d)
