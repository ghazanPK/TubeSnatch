"""Locate bundled resources and helper binaries (FFmpeg, Deno).

In the Windows builds the helpers live in ``<app>/bin`` (portable build) or
``_internal/bin`` (PyInstaller build).
During development we fall back to the system PATH / the ``deno`` wheel.
"""

from __future__ import annotations

import os
import shutil
import sys
from functools import cache
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
EXE_SUFFIX = ".exe" if os.name == "nt" else ""


def app_root() -> Path:
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def asset(name: str) -> Path:
    return app_root() / "assets" / name


def _bundled(name: str) -> Path | None:
    exe_dir = Path(sys.executable).resolve().parent
    candidates = [
        app_root() / "bin" / f"{name}{EXE_SUFFIX}",  # PyInstaller: _internal/bin
        exe_dir / "bin" / f"{name}{EXE_SUFFIX}",
        exe_dir.parent / "bin" / f"{name}{EXE_SUFFIX}",  # venv-style layouts (dev: <venv>/bin/deno)
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


@cache
def ffmpeg_dir() -> str | None:
    """Directory containing ffmpeg + ffprobe, or None if not found."""
    bundled = _bundled("ffmpeg")
    if bundled:
        return str(bundled.parent)
    found = shutil.which("ffmpeg")
    return str(Path(found).parent) if found else None


@cache
def deno_path() -> str | None:
    """Path to the Deno JS runtime yt-dlp uses to solve YouTube challenges."""
    bundled = _bundled("deno")
    if bundled:
        return str(bundled)
    try:  # the `deno` wheel from PyPI ships the binary
        import deno

        p = deno.find_deno_bin()
        if p and Path(p).is_file():
            return str(p)
    except Exception:
        pass
    return shutil.which("deno")
