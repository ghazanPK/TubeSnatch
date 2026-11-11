"""Render README screenshots (docs/screenshots/*.png) from the real UI, offscreen.

Uses the CC BY "Blender Open Movies" playlist by Blender Studio so the images are safe to publish.
Settings are redirected to a temp folder, so your own settings and history are untouched.
On Windows, run it on the real display (the offscreen platform has no fonts there); the window
shows for ~20 s:

    dist\\TubeSnatch\\python.exe scripts\\make_screenshots.py
"""

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QStandardPaths.setTestModeEnabled(True)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())

from tubesnatch import engine, paths  # noqa: E402
from tubesnatch.ui import theme  # noqa: E402
from tubesnatch.ui.download_tab import C_FMT, C_QUAL  # noqa: E402
from tubesnatch.ui.main_window import MainWindow  # noqa: E402
from tubesnatch.ui.row_dialog import RowOptionsDialog  # noqa: E402
from tubesnatch.ui.about import AboutDialog  # noqa: E402
from tubesnatch.ui.widgets import select_data  # noqa: E402

PLAYLIST = "https://www.youtube.com/playlist?list=PLav47HAVZMjnTFVZL-aImCQIC0uLZtNCz"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
DEMO_DEST = r"D:\Media\TubeSnatch" if os.name == "nt" else "/home/you/Media/TubeSnatch"

app = QApplication(sys.argv[:1])
app.setStyle("Fusion")
app.setStyleSheet(theme.stylesheet(str(paths.asset(""))))
from tubesnatch.ui.config import Config  # noqa: E402

Config().set("update_mode", "off")  # no update dialogs while rendering
w = MainWindow()
w.resize(1240, 900)
w.show()
tab = w.download
tab.dest_input.setText(DEMO_DEST)
tab.mode_audio.setChecked(True)
tab._mode_changed()


def save(widget, name):
    for _ in range(3):  # let pending layout updates (from setText etc.) run before grabbing
        app.processEvents()
    widget.grab().save(str(OUT / f"{name}.png"))
    print("saved", name, flush=True)


def stage_download():
    rows = tab.rows

    def idx(word):
        return next((i for i, r in enumerate(rows) if word in r.entry.title.lower()), None)

    # a believable mix of states and per-row choices on the rows visible in the screenshot
    plan = [(0, "done"), (1, "running"), (2, "flac"), (3, "trim"), (4, "video"), (5, "chapters"), (6, "queued")]
    for i, what in plan:
        if i >= len(rows):
            continue
        r = rows[i]
        if what == "done":
            r.state = "done"
            tab._set_row_ui(i, 1000, "✓ Saved", "done")
            tab.table.item(i, 0).setCheckState(Qt.CheckState.Unchecked)
        elif what == "running":
            r.state = "running"
            tab._set_row_ui(i, 620, "62% · 3.4 MB/s · ETA 0:09", "")
        elif what == "queued":
            r.state = "queued"
            tab._set_row_ui(i, 0, "Queued", "")
        elif what == "trim":
            r.trim = (35, 95)
            tab._update_title(i)
        elif what == "chapters":
            r.split = True
            tab._update_title(i)
        elif what == "flac":
            select_data(tab._cell(i, C_FMT), "flac")
        elif what == "video":
            select_data(tab._cell(i, C_FMT), "mp4")
            select_data(tab._cell(i, C_QUAL), 1080)
    tab._refresh_counts()
    tab.overall_lbl.setText("Downloading… 1 done · 2 in progress")
    tab.overall.setValue(260)
    tab.set_status("Added 18 videos from “Blender Open Movies”.", "ok")
    save(w, "download")

    i = idx("wing it") or 3
    dlg = RowOptionsDialog(w, rows[i].entry.title, rows[i].entry.duration, rows[i].trim, False)
    dlg.resize(520, 330)
    dlg.show()
    QTimer.singleShot(300, lambda: (save(dlg, "trim"), dlg.close(), QTimer.singleShot(200, stage_convert)))


def stage_convert():
    w.show_page(1)
    c = w.convert
    demo = Path(tempfile.mkdtemp())
    names = ["Holiday in Lisbon.mov", "Podcast episode 12.wav", "Lecture - Signals and Systems.mkv",
             "Drone footage 4K.mp4", "Voice memo.m4a"]
    for n in names:
        (demo / n).write_bytes(b"0")
    c.add_files([str(demo / n) for n in names])
    c.out_input.setText(r"D:\Media\Converted" if os.name == "nt" else "/home/you/Media/Converted")
    folders = [r"D:\Videos\Travel", r"D:\Audio\Podcast", r"D:\University", r"D:\Videos\Drone", r"D:\Audio"]
    for i, f in enumerate(folders):
        c.table.item(i, 1).setText(f)
    select_data(c.target, "mp4")
    c._target_changed()
    select_data(c.quality, 1080)
    for i in range(2):
        c.table.item(i, 2).setText("MP4")
    c._set(0, 1000, "✓ Holiday in Lisbon.mp4", "done")
    c._set(1, 430, "Converting… 43%", "")
    c.rows[0].state, c.rows[1].state = "done", "running"
    c._refresh()
    c.overall_lbl.setText("Converting 4 files…")
    save(w, "convert")
    QTimer.singleShot(200, stage_settings)


def stage_settings():
    w.show_page(2)
    w.settings.mode.blockSignals(True)  # show the default choice, without changing the (temp) setting
    select_data(w.settings.mode, "notify")
    w.settings.mode.blockSignals(False)
    w.settings.set_app_status("You're on the latest version.")
    w.settings.set_engine_status(f"yt-dlp {engine.ytdlp_version()} is the latest stable version.")
    save(w, "settings")
    about = AboutDialog(w)
    about.show()
    QTimer.singleShot(300, lambda: (save(about, "about"), os._exit(0)))


def wait_for_rows(tries=[0]):
    tries[0] += 1
    if tab.rows:
        QTimer.singleShot(9000, stage_download)  # let thumbnails arrive
    elif tries[0] > 120:
        print("fetch failed")
        app.quit()
    else:
        QTimer.singleShot(500, wait_for_rows)


tab.fetch(PLAYLIST)
QTimer.singleShot(500, wait_for_rows)
app.exec()
os._exit(0)  # don't wait for idle network/thread-pool workers
