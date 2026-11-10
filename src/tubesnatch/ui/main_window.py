"""Main application window: header + navigation, tabs, log, status bar."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, engine, paths
from .about import AboutDialog
from .config import Config
from .convert_tab import ConvertTab
from .download_tab import DownloadTab
from .settings_tab import SettingsTab
from .update_flow import UpdateManager
from .widgets import button, label

YT_LINK = re.compile(r"^https?://(www\.|m\.|music\.)?(youtube\.com/(watch|playlist|shorts|live)|youtu\.be/)\S+$")


class MainWindow(QMainWindow):
    def __init__(self, updated: bool = False):
        super().__init__()
        self.setWindowTitle("TubeSnatch — video & playlist downloader")
        self.setWindowIcon(QIcon(str(paths.asset("icon.svg"))))
        self.resize(1240, 840)
        self.setMinimumSize(1100, 700)
        self.setAcceptDrops(True)
        self._force_quit = False
        self._last_clip = ""

        self.cfg = Config()
        self.download = DownloadTab(self.cfg)
        self.convert = ConvertTab(self.cfg)
        self.settings = SettingsTab(self.cfg, lambda: len(self.download.archive), self._clear_archive)
        self.updater = UpdateManager(self, self.cfg, self.settings)
        self.download.restart_guard = self.updater.guard

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 10)
        root.setSpacing(14)
        root.addLayout(self._build_header())

        self.pages = QStackedWidget()
        for page in (self.download, self.convert, self.settings):
            self.pages.addWidget(page)
        root.addWidget(self.pages, 1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.log_view.setFixedHeight(150)
        self.log_view.hide()
        root.addWidget(self.log_view)
        self._build_statusbar()

        for src in (self.download.log, self.convert.log, self.updater.log):
            src.connect(self.append_log)
        self.updater.badge.connect(self._set_badge)
        self.download.busy_changed.connect(lambda busy: None if busy else self._jobs_maybe_idle())
        self.settings.history_cleared.connect(self.download._apply_skip)
        QApplication.clipboard().dataChanged.connect(self._clipboard_changed)

        geo = self.cfg.raw("geometry")
        if geo:
            self.restoreGeometry(geo)
        self._check_tools()
        if updated:
            self.download.set_status(f"Updated to TubeSnatch v{__version__} ✓", "ok")
        self.updater.startup()

    # ----------------------------------------------------------------- layout

    def _build_header(self):
        h = QHBoxLayout()
        h.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(QIcon(str(paths.asset("icon.svg"))).pixmap(44, 44))
        h.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label("TubeSnatch", "brand"))
        titles.addWidget(label("Videos & playlists → MP4 / MP3", "tagline"))
        h.addLayout(titles)
        h.addSpacing(18)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        self.nav_group = QButtonGroup(self)
        for i, text in enumerate(("⬇  Download", "🔄  Convert", "⚙  Settings")):
            b = button(text, "nav")
            b.setCheckable(True)
            b.setChecked(i == 0)
            self.nav_group.addButton(b, i)
            nav.addWidget(b)
        self.nav_group.idClicked.connect(self.show_page)
        h.addLayout(nav)
        h.addStretch(1)

        self.badge_btn = button("", "badge", tip="Click for details")
        self.badge_btn.hide()
        self.badge_btn.clicked.connect(self.updater.badge_clicked)
        h.addWidget(self.badge_btn)
        about = button("About && credits", "ghost")
        about.clicked.connect(lambda: AboutDialog(self).exec())
        h.addWidget(about)
        return h

    def _build_statusbar(self):
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        links = [
            ("yt-dlp", "https://github.com/yt-dlp/yt-dlp"),
            ("FFmpeg", "https://ffmpeg.org"),
            ("Deno", "https://deno.com"),
            ("SponsorBlock", "https://sponsor.ajay.app"),
            ("Qt for Python", "https://doc.qt.io/qtforpython-6/"),
        ]
        credit = QLabel("Powered by " + " · ".join(
            f'<a style="color:#9d86ff;text-decoration:none" href="{u}">{n}</a>' for n, u in links))
        credit.setOpenExternalLinks(True)
        credit.setTextFormat(Qt.TextFormat.RichText)
        sb.addWidget(credit)
        self.log_btn = button("Show log", "ghost")
        self.log_btn.clicked.connect(self._toggle_log)
        sb.addPermanentWidget(self.log_btn)
        self.tools_lbl = QLabel()
        sb.addPermanentWidget(self.tools_lbl)

    def show_page(self, i: int):
        self.pages.setCurrentIndex(i)
        self.nav_group.button(i).setChecked(True)
        if i == 2:
            self.settings.refresh_history()

    # ----------------------------------------------------------------- status

    def _check_tools(self):
        bits = [
            "FFmpeg ✓" if paths.ffmpeg_dir() else "FFmpeg ✗",
            "Deno ✓" if paths.deno_path() else "Deno ✗",
            f"yt-dlp {engine.ytdlp_version()}",
            f"v{__version__}",
        ]
        self.tools_lbl.setText("   ".join(bits))
        if not paths.ffmpeg_dir():
            self.download.set_status("FFmpeg was not found — audio conversion and HD merging will fail.", "error")

    def _set_badge(self, text: str):
        self.badge_btn.setText(text)
        self.badge_btn.setVisible(bool(text))

    def append_log(self, msg: str):
        self.log_view.appendPlainText(msg.rstrip())

    def _toggle_log(self):
        vis = not self.log_view.isVisible()
        self.log_view.setVisible(vis)
        self.log_btn.setText("Hide log" if vis else "Show log")

    def _clear_archive(self):
        self.download.archive.clear()
        for r in self.download.rows:
            if r.state == "archived":
                r.state = "idle"

    # ----------------------------------------------------------------- jobs

    def active_jobs(self) -> int:
        return self.download.active_count() + self.convert.active_count()

    def _jobs_maybe_idle(self):
        if not self.active_jobs():
            self.updater.on_jobs_idle()

    def confirm_quit_with_jobs(self, action: str) -> bool:
        n = self.active_jobs()
        if not n:
            return True
        ans = QMessageBox.question(self, "Jobs in progress",
                                   f"{n} download(s)/conversion(s) are still running. Cancel them and {action}?")
        if ans != QMessageBox.StandardButton.Yes:
            return False
        self.download.cancel_all()
        self.convert.cancel_all()
        self.download.dl_pool.waitForDone(4000)
        self.convert.pool.waitForDone(4000)
        return True

    def quit_now(self):
        self._force_quit = True
        self.close()

    # ----------------------------------------------------------------- input

    def _clipboard_changed(self):
        if not self.cfg.get("watch_clipboard"):
            return
        text = QApplication.clipboard().text().strip()
        if text == self._last_clip or not YT_LINK.match(text):
            return
        self._last_clip = text
        self.show_page(0)
        self.download.fetch(text)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        local = [u.toLocalFile() for u in md.urls() if u.isLocalFile()] if md.hasUrls() else []
        if local:
            self.show_page(1)
            self.convert.add_files(local)
            return
        urls = [u.toString() for u in md.urls()] if md.hasUrls() else md.text().split()
        web = [u for u in urls if u.startswith("http")]
        if web:
            self.show_page(0)
        for i, u in enumerate(web):
            QTimer.singleShot(i * 150, lambda u=u: self.download.fetch(u))

    def closeEvent(self, e):
        if not self._force_quit and not self.confirm_quit_with_jobs("quit"):
            e.ignore()
            return
        self.download.save_settings()
        self.cfg.set_raw("geometry", self.saveGeometry())
        self.cfg.s.sync()  # the portable launcher hard-exits, so flush settings now
        self.updater.on_close()
        e.accept()
