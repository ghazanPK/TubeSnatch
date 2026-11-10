"""Update checks and installs for the app (GitHub Releases) and the engine (yt-dlp from PyPI)."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from .. import __version__, updates
from .config import Config
from .workers import TaskWorker

CHECK_INTERVAL = 20 * 3600  # automatic checks at most once a day-ish


class UpdateManager(QObject):
    badge = Signal(str)  # header badge text ("" hides it)
    log = Signal(str)

    def __init__(self, window, cfg: Config, settings_tab):
        super().__init__(window)
        self.win = window
        self.cfg = cfg
        self.st = settings_tab
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.release: updates.ReleaseInfo | None = None
        self.staged: Path | None = None
        self.engine_restart_pending = False
        self._engine_deferred: updates.EngineInfo | None = None
        self._downloading = False
        st = settings_tab
        st.check_app_requested.connect(lambda: self.check_app(manual=True))
        st.engine_update_requested.connect(lambda: self.check_engine(manual=True))

    # ----------------------------------------------------------------- startup

    def startup(self):
        self._run(updates.cleanup_staging)
        if updates.is_portable():
            failed = updates.app_dir() / "update-failed.txt"
            if failed.exists():
                QTimer.singleShot(800, lambda: QMessageBox.warning(self.win, "Update incomplete",
                                                                   failed.read_text(encoding="utf-8")))
        if self.cfg.get("update_mode") == "off":
            return
        if time.time() - self.cfg.get("last_update_check") < CHECK_INTERVAL:
            return
        QTimer.singleShot(2500, lambda: self.check_app(manual=False))

    def _run(self, fn, *args, done=None, failed=None, progress=None, **kwargs):
        w = TaskWorker(fn, *args, with_progress=progress is not None, **kwargs)
        if done:
            w.signals.done.connect(done)
        if failed:
            w.signals.failed.connect(failed)
        if progress:
            w.signals.progress.connect(progress)
        self.pool.start(w)

    # ----------------------------------------------------------------- app releases

    def check_app(self, manual: bool):
        self.st.set_busy(app=True)
        self.st.set_app_status("Checking GitHub for a new release…")
        self._run(updates.check_app, done=lambda info: self._app_checked(manual, info),
                  failed=lambda msg: self._app_failed(manual, msg))

    def _app_failed(self, manual: bool, msg: str):
        self.st.set_busy(app=False)
        self.st.set_app_status(f"Couldn't check for updates: {msg}")
        self.log.emit(f"Update check failed: {msg}")
        if manual:
            QMessageBox.warning(self.win, "Update check failed", f"Couldn't reach GitHub:\n{msg}")
        elif updates.is_portable():
            self.check_engine(manual=False)

    def _app_checked(self, manual: bool, info: updates.ReleaseInfo | None):
        self.st.set_busy(app=False)
        self.cfg.set("last_update_check", time.time())
        if info is None:
            self.st.set_app_status(f"You're on the latest version (v{__version__}). Checked {time.strftime('%H:%M')}.")
            if manual:
                QMessageBox.information(self.win, "No update", f"TubeSnatch v{__version__} is the latest version.")
            elif updates.is_portable():
                self.check_engine(manual=False)  # no new release — maybe just a newer yt-dlp
            return
        self.release = info
        self.st.set_app_status(f"Version {info.version} is available.")
        self.badge.emit(f"⬆  Update to v{info.version}")
        if not manual and self.cfg.get("skipped_version") == info.version:
            return
        if not updates.is_portable():
            self._prompt_external(info)
        elif self.cfg.get("update_mode") == "auto" and not manual:
            self.download(info)
        else:
            self.prompt(info)

    def _prompt_external(self, info: updates.ReleaseInfo):
        box = QMessageBox(self.win)
        box.setWindowTitle("Update available")
        box.setText(f"<b>TubeSnatch {info.version}</b> is available (you have {__version__}).")
        box.setInformativeText("This copy can't update itself (it isn't the portable Windows build). "
                               "Open the release page?")
        open_b = box.addButton("Open release page", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_b:
            QDesktopServices.openUrl(QUrl(info.html_url))

    def prompt(self, info: updates.ReleaseInfo):
        box = QMessageBox(self.win)
        box.setWindowTitle("Update available")
        box.setText(f"<b>TubeSnatch {info.version}</b> is available — you have {__version__}.")
        notes = info.notes.strip()
        if len(notes) > 900:
            notes = notes[:900].rsplit("\n", 1)[0] + "\n…"
        box.setInformativeText(f"Download size: {info.size / 1e6:.0f} MB. Your settings and download history are kept.")
        if notes:
            box.setDetailedText(notes)
        now = box.addButton("Update now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        skip = box.addButton("Skip this version", QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        if box.clickedButton() is now:
            self.download(info, then_install=True)
        elif box.clickedButton() is skip:
            self.cfg.set("skipped_version", info.version)
            self.badge.emit("")

    def download(self, info: updates.ReleaseInfo, then_install: bool = False):
        if self.staged is not None:
            self._ready(info, then_install)
            return
        if self._downloading:
            return
        self._downloading = True
        self.st.set_app_status(f"Downloading TubeSnatch {info.version}…")

        def prog(frac):
            pct = f"{int(frac * 100)}%" if frac is not None else "…"
            self.badge.emit(f"⬇  Downloading update {pct}")

        def done(path):
            self._downloading = False
            self.staged = Path(path)
            self.log.emit(f"Update {info.version} staged at {path}")
            self._ready(info, then_install)

        def failed(msg):
            self._downloading = False
            self.badge.emit(f"⬆  Update to v{info.version}")
            self.st.set_app_status(f"Update download failed: {msg}")
            QMessageBox.warning(self.win, "Update failed", f"Couldn't download the update:\n{msg}")

        self._run(updates.download_release, info, done=done, failed=failed, progress=prog)

    def _ready(self, info: updates.ReleaseInfo, install_now: bool):
        self.badge.emit(f"↻  Restart to update to v{info.version}")
        self.st.set_app_status(f"TubeSnatch {info.version} is downloaded and ready to install.")
        if install_now:
            self.install_now()
            return
        box = QMessageBox(self.win)
        box.setWindowTitle("Update ready")
        box.setText(f"<b>TubeSnatch {info.version}</b> is ready to install.")
        box.setInformativeText("Restart now, or it installs automatically when you close TubeSnatch.")
        now = box.addButton("Restart now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is now:
            self.install_now()

    def install_now(self):
        if self.staged is None:
            return
        if not self.win.confirm_quit_with_jobs("install the update"):
            return
        try:
            updates.apply_update(self.staged, relaunch=True)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self.win, "Update failed", str(e))
            return
        self.staged = None
        self.win.quit_now()

    def on_close(self):
        """Install a staged update silently while TubeSnatch exits."""
        if self.staged is not None:
            try:
                updates.apply_update(self.staged, relaunch=False)
            except Exception as e:  # noqa: BLE001
                self.log.emit(f"Couldn't install the update on exit: {e}")

    # ----------------------------------------------------------------- engine (yt-dlp)

    def check_engine(self, manual: bool):
        if not updates.is_portable():
            return
        if self.engine_restart_pending:
            self.ask_restart()
            return
        channel = self.cfg.get("engine_channel")
        self.st.set_busy(engine_busy=True)
        self.st.set_engine_status(f"Checking PyPI for the latest {channel} yt-dlp…")
        self._run(updates.check_engine, channel, done=lambda info: self._engine_checked(manual, info),
                  failed=lambda msg: self._engine_failed(msg))

    def _engine_failed(self, msg: str):
        self.st.set_busy(engine_busy=False)
        self.st.set_engine_status(f"Couldn't check yt-dlp: {msg}")
        self.log.emit(f"yt-dlp check failed: {msg}")

    def _engine_checked(self, manual: bool, info: updates.EngineInfo):
        self.st.set_busy(engine_busy=False)
        if not info.update_available:
            self.st.set_engine_status(f"yt-dlp {info.installed} is the latest {info.channel} version.")
            if manual:
                QMessageBox.information(self.win, "yt-dlp", f"yt-dlp {info.installed} is up to date.")
            return
        self.st.set_engine_status(f"yt-dlp {info.latest} is available (you have {info.installed}).")
        if manual or self.cfg.get("update_mode") == "auto":
            self.install_engine(info)
            return
        box = QMessageBox(self.win)
        box.setWindowTitle("Engine update")
        box.setText(f"A newer download engine is available: <b>yt-dlp {info.latest}</b> (you have {info.installed}).")
        box.setInformativeText("Updating keeps YouTube downloads working. It takes a few seconds.")
        now = box.addButton("Update now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is now:
            self.install_engine(info)

    def install_engine(self, info: updates.EngineInfo):
        if self.win.active_jobs():
            self._engine_deferred = info
            self.st.set_engine_status(f"yt-dlp {info.latest} will be installed when the current downloads finish.")
            return
        self.st.set_busy(engine_busy=True)
        self.st.set_engine_status(f"Installing yt-dlp {info.latest}…")
        self.badge.emit("⬇  Updating yt-dlp…")

        def done(version):
            self.st.set_busy(engine_busy=False)
            self.engine_restart_pending = True
            self.st.set_engine_version(f"{version} (restart to use)")
            self.st.set_engine_status(f"yt-dlp {version} installed. Restart TubeSnatch to start using it.")
            self.badge.emit("↻  Restart to finish yt-dlp update")
            self.ask_restart(f"yt-dlp was updated to {version}.")

        def failed(msg):
            self.st.set_busy(engine_busy=False)
            self.badge.emit("")
            self.st.set_engine_status(f"yt-dlp update failed: {msg}")
            QMessageBox.warning(self.win, "yt-dlp update failed", msg)

        self._run(updates.upgrade_engine, info, log=self.log.emit, done=done, failed=failed)

    def on_jobs_idle(self):
        if self._engine_deferred is not None:
            info, self._engine_deferred = self._engine_deferred, None
            self.install_engine(info)

    def ask_restart(self, headline: str = "yt-dlp was updated.") -> bool:
        box = QMessageBox(self.win)
        box.setWindowTitle("Restart needed")
        box.setText(f"<b>{headline}</b>")
        box.setInformativeText("TubeSnatch needs a quick restart to use the new download engine.")
        now = box.addButton("Restart now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is now:
            self.restart()
            return True
        return False

    def restart(self):
        if not self.win.confirm_quit_with_jobs("restart"):
            return
        updates.restart_app()
        self.win.quit_now()

    def guard(self) -> bool:
        """Called before fetching/downloading. Blocks new work until a pending engine restart happens."""
        if not self.engine_restart_pending:
            return True
        self.ask_restart("yt-dlp was updated — restart first.")
        return False

    def badge_clicked(self):
        if self.staged is not None and self.release is not None:
            self._ready(self.release, install_now=False)
        elif self.release is not None and not self._downloading:
            if updates.is_portable():
                self.prompt(self.release)
            else:
                self._prompt_external(self.release)
        elif self.engine_restart_pending:
            self.ask_restart()
