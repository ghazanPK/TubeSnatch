"""TubeSnatch — a friendly GUI for downloading videos and playlists with yt-dlp."""

__version__ = "1.1.0"

# GitHub "owner/name" that publishes releases; the in-app updater checks it.
GITHUB_REPO = "ghazanPK/TubeSnatch"


def main(exit_process: bool = True) -> int:
    import sys

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication

    from . import paths
    from .ui import theme
    from .ui.main_window import MainWindow

    if sys.platform == "win32":
        try:  # own taskbar icon instead of python's
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TubeSnatch.App")
        except Exception:
            pass

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("TubeSnatch")
    app.setOrganizationName("TubeSnatch")
    app.setWindowIcon(QIcon(str(paths.asset("icon.svg"))))
    app.setStyle("Fusion")
    app.setStyleSheet(theme.stylesheet(str(paths.asset(""))))

    import os

    updated = "--updated" in sys.argv or os.environ.pop("TUBESNATCH_UPDATED", "") == "1"
    win = MainWindow(updated=updated)
    win.show()
    for arg in sys.argv[1:]:
        if arg.startswith("http"):
            win.download.fetch(arg)
    code = app.exec()
    if exit_process:
        sys.exit(code)
    return code
