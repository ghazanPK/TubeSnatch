"""Small helpers for running the bundled FFmpeg directly (converter, loudness normalisation)."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Callable

from . import paths

NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: no console flash


class FFmpegError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


def exe(name: str = "ffmpeg") -> str:
    d = paths.ffmpeg_dir()
    if d:
        p = Path(d) / f"{name}{paths.EXE_SUFFIX}"
        if p.is_file():
            return str(p)
    found = shutil.which(name)
    if not found:
        raise FFmpegError(f"{name} was not found")
    return found


def probe(path: str) -> dict:
    """Return {'duration': float|None, 'has_video': bool, 'has_audio': bool}."""
    out = subprocess.run(
        [exe("ffprobe"), "-v", "error", "-show_entries", "format=duration:stream=codec_type,disposition",
         "-of", "json", path],
        capture_output=True, text=True, creationflags=NO_WINDOW, check=False,
    )
    import json

    try:
        data = json.loads(out.stdout or "{}")
    except ValueError:
        data = {}
    streams = data.get("streams") or []
    video = [s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    dur = (data.get("format") or {}).get("duration")
    return {
        "duration": float(dur) if dur not in (None, "N/A") else None,
        "has_video": bool(video),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def run(
    args: list[str],
    duration: float | None = None,
    on_progress: Callable[[float | None], None] | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Run ffmpeg with ``args`` (inputs + outputs). Reports 0..1 progress when duration is known."""
    cmd = [exe("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        creationflags=NO_WINDOW,
    )
    tail: deque[str] = deque(maxlen=25)
    t = threading.Thread(target=lambda: [tail.append(line.rstrip()) for line in proc.stderr], daemon=True)
    t.start()
    assert proc.stdout is not None
    for line in proc.stdout:
        if cancel is not None and cancel.is_set():
            proc.kill()
            proc.wait()
            raise Cancelled("Cancelled")
        if on_progress and line.startswith("out_time_us=") and duration:
            try:
                us = int(line.split("=", 1)[1])
                on_progress(max(0.0, min(1.0, us / 1e6 / duration)))
            except ValueError:
                pass
    proc.wait()
    t.join(timeout=2)
    if cancel is not None and cancel.is_set():
        raise Cancelled("Cancelled")
    if proc.returncode != 0:
        msg = next((ln for ln in reversed(tail) if ln and not ln.startswith("[")), "") or "\n".join(tail)
        raise FFmpegError(f"FFmpeg failed: {msg}")
