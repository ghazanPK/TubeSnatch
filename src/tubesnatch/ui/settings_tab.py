"""Settings tab: playlists, extras, network, updates, shortcuts."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, engine, updates
from .config import Config
from .widgets import button, card, label, select_data


def _section(title: str, subtitle: str = "") -> tuple[QFrame, QGridLayout]:
    c = card()
    g = QGridLayout(c)
    g.setContentsMargins(18, 14, 18, 16)
    g.setHorizontalSpacing(14)
    g.setVerticalSpacing(10)
    g.addWidget(label(title, "sectionTitle"), 0, 0, 1, 4)
    if subtitle:
        g.addWidget(label(subtitle, "muted", wrap=True), 1, 0, 1, 4)
    g.setColumnStretch(3, 1)
    return c, g


class SettingsTab(QWidget):
    check_app_requested = Signal()
    engine_update_requested = Signal()
    history_cleared = Signal()

    def __init__(self, config: Config, archive_count, clear_archive, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._archive_count = archive_count
        self._clear_archive = clear_archive

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        inner = QWidget()
        cols = QHBoxLayout(inner)
        cols.setContentsMargins(0, 0, 6, 0)
        cols.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)
        right = QVBoxLayout()
        right.setSpacing(14)
        left.addWidget(self._downloads_section())
        left.addWidget(self._extras_section())
        left.addStretch(1)
        right.addWidget(self._updates_section())
        if updates.is_portable():
            right.addWidget(self._shortcuts_section())
        right.addStretch(1)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # ----------------------------------------------------------------- helpers

    def _check(self, text: str, key: str, tip: str = "") -> QCheckBox:
        c = QCheckBox(text)
        c.setChecked(self.cfg.get(key))
        c.toggled.connect(lambda on: self.cfg.set(key, on))
        if tip:
            c.setToolTip(tip)
        return c

    # ----------------------------------------------------------------- sections

    def _downloads_section(self):
        c, g = _section("PLAYLISTS & HISTORY")
        g.addWidget(self._check("Save playlists into a folder named after the playlist", "subdir"), 2, 0, 1, 4)
        g.addWidget(self._check("Number playlist files by position (007 - Title.mp3)", "number"), 3, 0, 1, 4)
        self.hist_lbl = label("", "muted")
        g.addWidget(self.hist_lbl, 4, 0, 1, 2)
        clear = button("Forget download history", tip="Videos will no longer show as “downloaded before”.")
        clear.clicked.connect(self._forget_history)
        g.addWidget(clear, 4, 2)
        self.refresh_history()
        return c

    def refresh_history(self):
        n = self._archive_count()
        self.hist_lbl.setText(f"Download history: {n} video{'s' if n != 1 else ''} remembered")

    def _forget_history(self):
        if QMessageBox.question(self, "Forget history", "Forget every video in your download history?\n"
                                "Playlists will show all videos as new again.") == QMessageBox.StandardButton.Yes:
            self._clear_archive()
            self.refresh_history()
            self.history_cleared.emit()

    def _extras_section(self):
        c, g = _section("EXTRAS")
        r = 1
        g.addWidget(label("Subtitles"), r, 0)
        self.subs = QComboBox()
        self.subs.addItem("Off", "off")
        self.subs.addItem("Embed into video", "embed")
        self.subs.addItem("Save as .srt files", "file")
        select_data(self.subs, self.cfg.get("subtitles"))
        self.subs.currentIndexChanged.connect(lambda _i: self.cfg.set("subtitles", self.subs.currentData()))
        g.addWidget(self.subs, r, 1)
        g.addWidget(label("Languages"), r, 2)
        langs = QLineEdit(self.cfg.get("sub_langs"))
        langs.setToolTip("yt-dlp language patterns, comma separated.\n"
                         "en.* = any English · en,de = English + German · all = everything")
        langs.editingFinished.connect(lambda: self.cfg.set("sub_langs", langs.text().strip() or "en.*"))
        g.addWidget(langs, r, 3)
        r += 1
        sb = self._check("Remove sponsor segments (SponsorBlock)", "sponsorblock",
                         "Cuts sponsor reads, self-promotion and 'subscribe' reminders,\n"
                         "using community-submitted segments from SponsorBlock (sponsor.ajay.app).")
        g.addWidget(sb, r, 0, 1, 4)
        r += 1
        g.addWidget(self._check("Normalise volume of audio files (EBU R128, −14 LUFS)", "normalize",
                                "Makes every track similarly loud — handy for playlists. Re-encodes the audio."),
                    r, 0, 1, 4)
        r += 1
        g.addWidget(self._check("Frame-accurate trimming (slower, re-encodes the cut points)", "accurate_cuts"),
                    r, 0, 1, 4)
        r += 1
        g.addWidget(self._check("Watch the clipboard and fetch copied YouTube links", "watch_clipboard"), r, 0, 1, 4)
        r += 1
        g.addWidget(label("Speed limit"), r, 0)
        rate = QComboBox()
        rate.setEditable(True)
        for text, val in (("Unlimited", ""), ("500 KB/s", "500K"), ("1 MB/s", "1M"), ("2 MB/s", "2M"),
                          ("5 MB/s", "5M"), ("10 MB/s", "10M")):
            rate.addItem(text, val)
        if not select_data(rate, self.cfg.get("rate_limit")):
            rate.setEditText(self.cfg.get("rate_limit"))

        def rate_changed():
            idx = rate.findText(rate.currentText())
            val = rate.itemData(idx) if idx >= 0 else rate.currentText().strip().upper().replace("B/S", "").replace(" ", "")
            if engine.valid_rate(val or ""):
                self.cfg.set("rate_limit", val or "")
        rate.currentIndexChanged.connect(lambda _i: rate_changed())
        rate.lineEdit().editingFinished.connect(rate_changed)
        rate.setToolTip("Per download. Custom values like 750K or 3M work too.")
        g.addWidget(rate, r, 1)
        return c

    def _updates_section(self):
        c, g = _section("UPDATES")
        portable = updates.is_portable()
        g.addWidget(label("TubeSnatch"), 2, 0)
        self.app_ver = label(f"v{__version__}", "pill")
        g.addWidget(self.app_ver, 2, 1)
        g.addWidget(label("When a new release is out"), 3, 0)
        self.mode = QComboBox()
        self.mode.addItem("Download & install it (ask to restart)", "auto")
        self.mode.addItem("Show a notification", "notify")
        self.mode.addItem("Don't check", "off")
        select_data(self.mode, self.cfg.get("update_mode"))
        self.mode.currentIndexChanged.connect(lambda _i: self.cfg.set("update_mode", self.mode.currentData()))
        g.addWidget(self.mode, 3, 1, 1, 3)
        self.check_btn = button("Check for updates now")
        self.check_btn.clicked.connect(self.check_app_requested)
        g.addWidget(self.check_btn, 4, 0, 1, 2)
        self.app_status = label("", "muted", wrap=True)
        g.addWidget(self.app_status, 5, 0, 1, 4)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #272c3b;")
        g.addWidget(line, 6, 0, 1, 4)

        g.addWidget(label("Download engine (yt-dlp)"), 7, 0)
        self.engine_ver = label(f"{engine.ytdlp_version()}", "pill")
        g.addWidget(self.engine_ver, 7, 1)
        g.addWidget(label("Channel"), 8, 0)
        self.channel = QComboBox()
        self.channel.addItem("Stable releases", "stable")
        self.channel.addItem("Nightly (fixes land first)", "nightly")
        select_data(self.channel, self.cfg.get("engine_channel"))
        self.channel.currentIndexChanged.connect(lambda _i: self.cfg.set("engine_channel", self.channel.currentData()))
        self.channel.setToolTip("If YouTube downloads break, nightly builds usually contain the fix days\n"
                                "before the next stable release.")
        g.addWidget(self.channel, 8, 1, 1, 3)
        self.engine_btn = button("Check && update yt-dlp")
        self.engine_btn.clicked.connect(self.engine_update_requested)
        g.addWidget(self.engine_btn, 9, 0, 1, 2)
        self.engine_status = label("", "muted", wrap=True)
        g.addWidget(self.engine_status, 10, 0, 1, 4)
        g.addWidget(label("YouTube changes often. Updating yt-dlp here fixes most broken downloads without "
                          "waiting for a new TubeSnatch release. Version info comes from PyPI and GitHub.",
                          "muted", wrap=True), 11, 0, 1, 4)
        if not portable:
            for w in (self.engine_btn, self.channel):
                w.setEnabled(False)
            self.engine_status.setText("Running from source — update with `uv lock --upgrade-package yt-dlp`.")
        return c

    def _shortcuts_section(self):
        c, g = _section("SHORTCUTS", "TubeSnatch is portable — no installer. Start it with TubeSnatch.exe in its "
                                     "folder, or add shortcuts (with the TubeSnatch icon) here.")
        desk = button("Add Desktop shortcut")
        start = button("Add to Start menu")
        status = label("", "muted")

        def make(desktop: bool, start_menu: bool):
            try:
                updates.ensure_shortcuts(desktop=desktop, start_menu=start_menu)
                status.setText("Shortcut created ✓")
            except Exception as e:  # noqa: BLE001
                status.setText(f"Couldn't create the shortcut: {e}")
        desk.clicked.connect(lambda: make(True, False))
        start.clicked.connect(lambda: make(False, True))
        g.addWidget(desk, 2, 0)
        g.addWidget(start, 2, 1)
        g.addWidget(status, 3, 0, 1, 4)
        return c

    # ----------------------------------------------------------------- status setters

    def set_app_status(self, text: str):
        self.app_status.setText(text)

    def set_engine_status(self, text: str):
        self.engine_status.setText(text)

    def set_engine_version(self, text: str):
        self.engine_ver.setText(text)

    def set_busy(self, app: bool | None = None, engine_busy: bool | None = None):
        if app is not None:
            self.check_btn.setEnabled(not app)
        if engine_busy is not None and updates.is_portable():
            self.engine_btn.setEnabled(not engine_busy)
