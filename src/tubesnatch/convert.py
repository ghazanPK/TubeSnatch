"""Local file converter (any media FFmpeg can read → MP4/MKV/WebM/MP3/M4A/Opus/FLAC/WAV)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import ffmpeg
from .engine import AUDIO_FORMATS, LOSSLESS, is_audio

TARGETS = ["mp4", "mkv", "webm", "mp3", "m4a", "opus", "flac", "wav"]
MEDIA_EXTS = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg", ".ts", ".3gp",
    ".mp3", ".m4a", ".aac", ".opus", ".ogg", ".oga", ".flac", ".wav", ".wma", ".aiff", ".aif", ".alac",
}
DEFAULT_KBPS = {"mp3": 320, "m4a": 256, "opus": 160}


@dataclass
class ConvertOptions:
    target: str = "mp3"
    quality: int = 0  # video: max height (0 = keep); audio: kbps (0 = default)
    copy_streams: bool = False  # video container change without re-encoding
    outdir: str | None = None  # None = next to the source file


def output_path(src: str, o: ConvertOptions) -> Path:
    s = Path(src)
    folder = Path(o.outdir) if o.outdir else s.parent
    out = folder / f"{s.stem}.{o.target}"
    n = 1
    while out.exists() or out.resolve() == s.resolve():
        suffix = " (converted)" if n == 1 else f" (converted {n})"
        out = folder / f"{s.stem}{suffix}.{o.target}"
        n += 1
    return out


def build_args(src: str, out: str, o: ConvertOptions, has_video: bool) -> list[str]:
    args = ["-i", src]
    t = o.target
    if is_audio(t) or not has_video:
        if not is_audio(t):
            raise ValueError("This file has no video stream — pick an audio format.")
        args += ["-map", "0:a:0", "-vn", "-map_metadata", "0"]
        args += {
            "mp3": ["-c:a", "libmp3lame", "-id3v2_version", "3"],
            "m4a": ["-c:a", "aac"],
            "opus": ["-c:a", "libopus"],
            "flac": ["-c:a", "flac"],
            "wav": ["-c:a", "pcm_s16le"],
        }[t]
        if t not in LOSSLESS:
            args += ["-b:a", f"{o.quality or DEFAULT_KBPS[t]}k"]
    elif o.copy_streams:
        args += ["-map", "0", "-c", "copy"]
        if t == "mp4":
            args += ["-movflags", "+faststart"]
    else:
        args += ["-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0"]
        if o.quality:
            args += ["-vf", f"scale=-2:'min({o.quality},ih)'"]
        if t == "webm":
            args += ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1", "-deadline", "good",
                     "-cpu-used", "4", "-c:a", "libopus", "-b:a", "160k"]
        else:
            args += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                     "-c:a", "aac", "-b:a", "192k"]
            if t == "mp4":
                args += ["-movflags", "+faststart"]
    args.append(out)
    return args


def convert(
    src: str,
    o: ConvertOptions,
    on_progress: Callable[[float | None], None],
    cancel: threading.Event,
) -> str:
    info = ffmpeg.probe(src)
    if not info["has_audio"] and not info["has_video"]:
        raise ValueError("No audio or video found in this file.")
    if o.target in AUDIO_FORMATS and not info["has_audio"]:
        raise ValueError("This file has no audio stream.")
    out = output_path(src, o)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        ffmpeg.run(build_args(src, str(out), o, info["has_video"]), info["duration"], on_progress, cancel)
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    return str(out)
