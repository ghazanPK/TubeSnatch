"""Typed access to persisted settings (QSettings)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

DEFAULTS: dict[str, object] = {
    # download defaults
    "mode": "audio",
    "video_fmt": "mp4",
    "audio_fmt": "mp3",
    "height": 1080,
    "kbps": 320,
    "dest": "",
    "thumb": True,
    "meta": True,
    "skip_downloaded": True,
    "split_chapters": False,
    "parallel": 3,
    # playlists
    "subdir": True,
    "number": True,
    # extras
    "subtitles": "off",  # off | embed | file
    "sub_langs": "en.*",
    "sponsorblock": False,
    "normalize": False,
    "accurate_cuts": True,
    "rate_limit": "",
    "watch_clipboard": False,
    # converter
    "conv_target": "mp3",
    "conv_outdir": "",
    "conv_same_folder": True,
    # updates
    "update_mode": "notify",  # auto | notify | off
    "engine_channel": "stable",  # stable | nightly
    "last_update_check": 0.0,
    "skipped_version": "",
}


class Config:
    def __init__(self):
        # INI file (not the registry) so a portable copy's settings are easy to find/reset and tests can redirect it
        self.s = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "TubeSnatch", "TubeSnatch")

    def get(self, key: str):
        default = DEFAULTS[key]
        v = self.s.value(key, default)
        if isinstance(default, bool):
            return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")
        if isinstance(default, int):
            try:
                return int(v)
            except (TypeError, ValueError):
                return default
        if isinstance(default, float):
            try:
                return float(v)
            except (TypeError, ValueError):
                return default
        return str(v) if v is not None else default

    def set(self, key: str, value) -> None:
        self.s.setValue(key, value)

    def raw(self, key: str, default=None):
        return self.s.value(key, default)

    def set_raw(self, key: str, value) -> None:
        self.s.setValue(key, value)

    @staticmethod
    def default_dest() -> str:
        dl = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        return str(Path(dl) / "TubeSnatch")

    @staticmethod
    def data_dir() -> Path:
        d = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        d.mkdir(parents=True, exist_ok=True)
        return d
