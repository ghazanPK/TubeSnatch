"""Download engine — a thin, Qt-free wrapper around yt-dlp.

All the heavy lifting (extraction, format selection, downloading, FFmpeg
post-processing) is done by yt-dlp: https://github.com/yt-dlp/yt-dlp
Options are built as yt-dlp CLI arguments and converted with
``yt_dlp.parse_options`` so behaviour matches the command-line tool exactly.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.utils import DownloadCancelled, sanitize_filename

from . import paths

VIDEO_HEIGHTS = [2160, 1440, 1080, 720, 480, 360, 240, 144]
AUDIO_BITRATES = [320, 256, 192, 128]  # kbps; 0 = best VBR (V0)


# --------------------------------------------------------------------------- data


@dataclass
class Entry:
    url: str
    id: str = ""
    title: str = "Untitled"
    uploader: str = ""
    duration: float | None = None
    thumbnail: str | None = None
    index: int = 1
    heights: list[int] = field(default_factory=list)  # empty = unknown → standard list


@dataclass
class ProbeResult:
    kind: str  # "video" | "playlist"
    title: str
    uploader: str
    thumbnail: str | None
    entries: list[Entry]
    webpage_url: str = ""


@dataclass
class JobOptions:
    outdir: str
    mode: str = "audio"  # "audio" | "video"
    height: int = 0  # 0 = best available
    container: str = "mp4"  # mp4 | mkv
    audio_kbps: int = 320  # 0 = best VBR
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    filename_prefix: str = ""  # e.g. "003 - " for playlist numbering


@dataclass
class Progress:
    fraction: float | None  # 0..1, None = indeterminate
    text: str


ProgressCallback = Callable[[Progress], None]


# --------------------------------------------------------------------------- helpers


def _base_args() -> list[str]:
    args: list[str] = []
    if d := paths.ffmpeg_dir():
        args += ["--ffmpeg-location", d]
    if js := paths.deno_path():
        args += ["--js-runtimes", f"deno:{js}"]
    return args


def _opts(args: list[str]) -> dict:
    opts = yt_dlp.parse_options(args).ydl_opts
    opts.update(quiet=True, no_warnings=False, noprogress=True, ignoreerrors=False)
    return opts


class _Logger:
    def __init__(self, sink: Callable[[str], None] | None):
        self.sink = sink

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug]"):
            return
        self.info(msg)

    def info(self, msg: str) -> None:
        if self.sink:
            self.sink(msg)

    def warning(self, msg: str) -> None:
        self.info(f"WARNING: {msg}")

    def error(self, msg: str) -> None:
        self.info(msg)


def _pick_thumb(item: dict, target_w: int = 336) -> str | None:
    thumbs = [t for t in item.get("thumbnails") or [] if t.get("url")]
    if thumbs:
        sized = [t for t in thumbs if t.get("width")]
        if sized:
            bigger = [t for t in sized if t["width"] >= target_w]
            pick = min(bigger, key=lambda t: t["width"]) if bigger else max(sized, key=lambda t: t["width"])
            return pick["url"]
        return thumbs[-1]["url"]
    return item.get("thumbnail")


def _heights(info: dict) -> list[int]:
    hs = {
        int(f["height"])
        for f in info.get("formats") or []
        if f.get("height") and f.get("vcodec") not in (None, "none")
    }
    return sorted(hs, reverse=True)


def fmt_duration(seconds: float | None) -> str:
    if not seconds:
        return "—"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_bytes(n: float | None) -> str:
    if not n:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# --------------------------------------------------------------------------- probe


def probe(url: str, log: Callable[[str], None] | None = None) -> ProbeResult:
    """Fetch metadata for a video or (flat) playlist without downloading."""
    opts = _opts(_base_args() + ["--flat-playlist", "--skip-download"])
    opts["logger"] = _Logger(log)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        raise RuntimeError("Nothing found at that URL.")

    if info.get("_type") in ("playlist", "multi_video") or "entries" in info:
        entries = []
        for i, e in enumerate(info.get("entries") or [], start=1):
            if not e:
                continue
            vurl = e.get("url") or e.get("webpage_url")
            if e.get("ie_key") == "Youtube" and e.get("id"):
                vurl = f"https://www.youtube.com/watch?v={e['id']}"
            if not vurl:
                continue
            title = e.get("title") or "Untitled"
            if title in ("[Private video]", "[Deleted video]"):
                continue
            entries.append(
                Entry(
                    url=vurl,
                    id=e.get("id", ""),
                    title=title,
                    uploader=e.get("channel") or e.get("uploader") or "",
                    duration=e.get("duration"),
                    thumbnail=_pick_thumb(e),
                    index=e.get("playlist_index") or i,
                )
            )
        if not entries:
            raise RuntimeError("The playlist is empty or all its videos are unavailable.")
        return ProbeResult(
            kind="playlist",
            title=info.get("title") or "Playlist",
            uploader=info.get("channel") or info.get("uploader") or "",
            thumbnail=_pick_thumb(info, 640) or entries[0].thumbnail,
            entries=entries,
            webpage_url=info.get("webpage_url") or url,
        )

    entry = Entry(
        url=info.get("webpage_url") or url,
        id=info.get("id", ""),
        title=info.get("title") or "Untitled",
        uploader=info.get("channel") or info.get("uploader") or "",
        duration=info.get("duration"),
        thumbnail=_pick_thumb(info),
        heights=_heights(info),
    )
    return ProbeResult(
        kind="video",
        title=entry.title,
        uploader=entry.uploader,
        thumbnail=_pick_thumb(info, 640),
        entries=[entry],
        webpage_url=entry.url,
    )


# --------------------------------------------------------------------------- download


def build_args(o: JobOptions) -> list[str]:
    args = _base_args() + ["--no-playlist", "-P", o.outdir, "-o", f"{o.filename_prefix}%(title)s.%(ext)s"]
    if o.mode == "audio":
        quality = f"{o.audio_kbps}K" if o.audio_kbps else "0"
        args += ["-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--audio-quality", quality]
    else:
        res = f"res:{o.height}" if o.height else "res"
        # MP4: at the chosen resolution prefer H.264 + AAC so it plays everywhere
        sort = f"{res},vcodec:h264,acodec:aac,ext:mp4:m4a" if o.container == "mp4" else res
        args += ["-f", "bv*+ba/b", "-S", sort, "--merge-output-format", o.container]
    if o.embed_metadata:
        args.append("--embed-metadata")
    if o.embed_thumbnail:
        args.append("--embed-thumbnail")
    return args


_PP_LABELS = {
    "ExtractAudio": "Converting to MP3…",
    "Merger": "Merging video + audio…",
    "EmbedThumbnail": "Embedding cover art…",
    "Metadata": "Writing tags…",
    "VideoConvertor": "Converting…",
    "ThumbnailsConvertor": "Preparing cover art…",
}


def download(
    url: str,
    options: JobOptions,
    on_progress: ProgressCallback,
    cancel: threading.Event,
    log: Callable[[str], None] | None = None,
) -> str:
    """Download one video. Returns the final file path. Raises on error/cancel."""
    Path(options.outdir).mkdir(parents=True, exist_ok=True)
    state = {"part": 0, "parts": 1}

    def hook(d: dict) -> None:
        if cancel.is_set():
            raise DownloadCancelled("Cancelled by user")
        status = d.get("status")
        if status == "downloading":
            info = d.get("info_dict") or {}
            state["parts"] = max(1, len(info.get("requested_formats") or [None]))
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            frac = (done / total) if total else None
            if frac is not None and state["parts"] > 1:
                frac = (state["part"] + frac) / state["parts"]
            speed = d.get("speed")
            eta = d.get("eta")
            bits = [f"{_fmt_bytes(done)} / {_fmt_bytes(total)}"]
            if speed:
                bits.append(f"{_fmt_bytes(speed)}/s")
            if eta is not None:
                bits.append(f"ETA {fmt_duration(eta) if eta else '0:00'}")
            if state["parts"] > 1:
                bits.insert(0, f"stream {state['part'] + 1}/{state['parts']}")
            on_progress(Progress(frac, " · ".join(bits)))
        elif status == "finished":
            state["part"] += 1

    def pp_hook(d: dict) -> None:
        if cancel.is_set():
            raise DownloadCancelled("Cancelled by user")
        if d.get("status") == "started":
            name = d.get("postprocessor", "")
            label = next((v for k, v in _PP_LABELS.items() if k in name), "Post-processing…")
            on_progress(Progress(None, label))

    opts = _opts(build_args(options))
    opts.update(progress_hooks=[hook], postprocessor_hooks=[pp_hook], logger=_Logger(log))

    on_progress(Progress(None, "Starting…"))
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if cancel.is_set():
            raise DownloadCancelled("Cancelled by user")
        reqs = (info or {}).get("requested_downloads") or []
        path = (reqs[-1].get("filepath") if reqs else None) or (info or {}).get("filepath") or ""
    return path


def playlist_folder(base: str, title: str) -> str:
    name = sanitize_filename(title, restricted=False).strip(" .") or "Playlist"
    return str(Path(base) / name)


def ytdlp_version() -> str:
    return yt_dlp.version.__version__
