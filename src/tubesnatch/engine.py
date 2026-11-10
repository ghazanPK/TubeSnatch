"""Download engine — a thin, Qt-free wrapper around yt-dlp.

All the heavy lifting (extraction, format selection, downloading, FFmpeg
post-processing, SponsorBlock, subtitles) is done by yt-dlp:
https://github.com/yt-dlp/yt-dlp
Options are built as yt-dlp CLI arguments and converted with
``yt_dlp.parse_options`` so behaviour matches the command-line tool exactly.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.utils import DownloadCancelled, sanitize_filename

from . import ffmpeg, paths

VIDEO_HEIGHTS = [2160, 1440, 1080, 720, 480, 360, 240, 144]
AUDIO_BITRATES = [320, 256, 192, 128]  # kbps; 0 = best VBR / codec default

VIDEO_FORMATS = ["mp4", "mkv", "webm"]
AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav"]
LOSSLESS = {"flac", "wav"}
FORMAT_LABELS = {
    "mp4": "MP4", "mkv": "MKV", "webm": "WebM",
    "mp3": "MP3", "m4a": "M4A (AAC)", "opus": "Opus", "flac": "FLAC", "wav": "WAV",
}
SPONSORBLOCK_CATEGORIES = "sponsor,selfpromo,interaction"


def is_audio(fmt: str) -> bool:
    return fmt in AUDIO_FORMATS


# --------------------------------------------------------------------------- data


@dataclass
class Entry:
    url: str
    id: str = ""
    extractor: str = "youtube"
    title: str = "Untitled"
    uploader: str = ""
    duration: float | None = None
    thumbnail: str | None = None
    index: int = 1
    heights: list[int] = field(default_factory=list)  # empty = unknown → standard list

    @property
    def archive_key(self) -> str:
        """Same format as yt-dlp's --download-archive file."""
        return f"{self.extractor.lower()} {self.id}" if self.id else ""


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
    fmt: str = "mp3"  # one of VIDEO_FORMATS + AUDIO_FORMATS
    quality: int = 0  # video: max height (0 = best); audio: kbps (0 = best)
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    filename_prefix: str = ""  # e.g. "003 - " for playlist numbering
    trim: tuple[float, float | None] | None = None  # (start, end) seconds; end None = to the end
    accurate_cuts: bool = True  # re-encode around trim cuts for frame accuracy
    split_chapters: bool = False
    subtitles: str = "off"  # off | embed | file
    sub_langs: str = "en.*"
    sponsorblock: bool = False
    rate_limit: str = ""  # e.g. "2M"; empty = unlimited
    normalize: bool = False  # EBU R128 loudness normalisation (audio formats)

    @property
    def mode(self) -> str:
        return "audio" if is_audio(self.fmt) else "video"


@dataclass
class Progress:
    fraction: float | None  # 0..1, None = indeterminate
    text: str


@dataclass
class DownloadResult:
    path: str  # main file, or the chapter folder when split
    files: list[str]


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
    if seconds is None or seconds < 0:
        return "—"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_time(text: str) -> float | None:
    """'90', '1:30', '01:02:03', '1:30.5' → seconds. Empty → None. Raises ValueError if invalid."""
    text = text.strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3 or any(p.strip() == "" for p in parts):
        raise ValueError(f"Invalid time: {text!r}")
    total = 0.0
    for p in parts:
        v = float(p)
        if v < 0:
            raise ValueError(f"Invalid time: {text!r}")
        total = total * 60 + v
    return total


def _fmt_bytes(n: float | None) -> str:
    if not n:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _stamp(seconds: float) -> str:
    """Filename-safe timestamp: 83 → '01m23s', 3723 → '1h02m03s'."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m:02d}m{s:02d}s"


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
                    extractor=(e.get("ie_key") or "youtube").lower(),
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
        extractor=(info.get("extractor_key") or "youtube").lower(),
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


def _name_stem(o: JobOptions) -> str:
    stem = f"{o.filename_prefix}%(title)s"
    if o.trim:
        start, end = o.trim
        stem += f" [{_stamp(start)}-{_stamp(end) if end is not None else 'end'}]"
    return stem


def build_args(o: JobOptions, with_subs: bool = True) -> list[str]:
    stem = _name_stem(o)
    args = _base_args() + ["--no-playlist", "-P", o.outdir, "-o", f"{stem}.%(ext)s"]

    if o.mode == "audio":
        args += ["-f", "bestaudio/best", "-x", "--audio-format", o.fmt]
        if o.fmt not in LOSSLESS:
            args += ["--audio-quality", f"{o.quality}K" if o.quality else "0"]
    else:
        res = f"res:{o.quality}" if o.quality else "res"
        sort = {
            # at the chosen resolution prefer codecs that play everywhere
            "mp4": f"{res},vcodec:h264,acodec:aac,ext:mp4:m4a",
            "webm": f"{res},vcodec:vp9,acodec:opus,ext:webm:webm",
        }.get(o.fmt, res)
        args += ["-f", "bv*+ba/b", "-S", sort, "--merge-output-format", o.fmt]

    if o.embed_metadata:
        args.append("--embed-metadata")
    # WAV and WebM can't hold cover art
    if o.embed_thumbnail and o.fmt not in ("wav", "webm"):
        args.append("--embed-thumbnail")

    if o.trim:
        start, end = o.trim
        args += ["--download-sections", f"*{start}-{end if end is not None else 'inf'}"]
        if o.accurate_cuts:
            args.append("--force-keyframes-at-cuts")
    elif o.split_chapters:
        args += ["--split-chapters", "-o", f"chapter:{stem}/%(section_number)02d - %(section_title)s.%(ext)s"]

    if with_subs and o.subtitles != "off":
        args += ["--write-subs", "--write-auto-subs", "--sub-langs", o.sub_langs or "en.*"]
        if o.subtitles == "embed" and o.mode == "video":
            args.append("--embed-subs")
        else:
            args += ["--convert-subs", "srt"]

    if o.sponsorblock:
        args += ["--sponsorblock-remove", SPONSORBLOCK_CATEGORIES]
    if o.rate_limit:
        args += ["--limit-rate", o.rate_limit]
    return args


_PP_LABELS = {
    "ExtractAudio": "Converting audio…",
    "Merger": "Merging video + audio…",
    "EmbedThumbnail": "Embedding cover art…",
    "Metadata": "Writing tags…",
    "VideoConvertor": "Converting…",
    "ThumbnailsConvertor": "Preparing cover art…",
    "SplitChapters": "Splitting chapters…",
    "SponsorBlock": "Fetching SponsorBlock segments…",
    "ModifyChapters": "Removing sponsor segments…",
    "EmbedSubtitle": "Embedding subtitles…",
    "SubtitlesConvertor": "Converting subtitles…",
}

_AUDIO_CODECS = {
    "mp3": ["-c:a", "libmp3lame"],
    "m4a": ["-c:a", "aac"],
    "opus": ["-c:a", "libopus"],
    "flac": ["-c:a", "flac"],
    "wav": ["-c:a", "pcm_s16le"],
}


def normalize_audio(path: str, fmt: str, kbps: int, cancel: threading.Event | None = None,
                    on_progress: Callable[[float | None], None] | None = None) -> None:
    """Loudness-normalise an audio file in place (EBU R128, -14 LUFS like most streaming services)."""
    src = Path(path)
    tmp = src.with_name(f"{src.stem}.norm-tmp{src.suffix}")
    args = ["-i", str(src), "-map", "0:a:0", "-map", "0:v?", "-c:v", "copy", "-map_metadata", "0",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", *_AUDIO_CODECS[fmt]]
    if fmt in ("mp3", "m4a", "opus"):
        args += ["-b:a", f"{kbps or {'mp3': 320, 'm4a': 256, 'opus': 160}[fmt]}k"]
    if fmt == "mp3":
        args += ["-id3v2_version", "3"]
    if fmt in ("m4a",):
        args += ["-disposition:v", "attached_pic"]
    args.append(str(tmp))
    dur = ffmpeg.probe(str(src)).get("duration")
    try:
        ffmpeg.run(args, dur, on_progress, cancel)
        os.replace(tmp, src)
    finally:
        if tmp.exists():
            tmp.unlink()


def download(
    url: str,
    options: JobOptions,
    on_progress: ProgressCallback,
    cancel: threading.Event,
    log: Callable[[str], None] | None = None,
) -> DownloadResult:
    """Download one video. Raises on error/cancel."""
    try:
        return _download(url, options, on_progress, cancel, log, with_subs=True)
    except yt_dlp.utils.DownloadError as e:
        # Subtitle fetches are often rate-limited; don't lose the whole download over them.
        if options.subtitles != "off" and "subtitle" in str(e).lower() and not cancel.is_set():
            if log:
                log("WARNING: subtitles failed to download — retrying without subtitles")
            return _download(url, options, on_progress, cancel, log, with_subs=False)
        raise


def _download(url, options: JobOptions, on_progress, cancel, log, with_subs: bool) -> DownloadResult:
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
                frac = (min(state["part"], state["parts"] - 1) + frac) / state["parts"]
            bits = [f"{int(frac * 100)}%" if frac is not None else _fmt_bytes(done)]
            if speed := d.get("speed"):
                bits.append(f"{_fmt_bytes(speed)}/s")
            eta = d.get("eta")
            if eta is not None:
                bits.append(f"ETA {fmt_duration(eta)}")
            if state["parts"] > 1:
                bits.insert(0, f"stream {min(state['part'] + 1, state['parts'])}/{state['parts']}")
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

    opts = _opts(build_args(options, with_subs=with_subs))
    opts.update(progress_hooks=[hook], postprocessor_hooks=[pp_hook], logger=_Logger(log))

    on_progress(Progress(None, "Starting…"))
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if cancel.is_set():
            raise DownloadCancelled("Cancelled by user")
        info = info or {}
        reqs = info.get("requested_downloads") or []
        path = (reqs[-1].get("filepath") if reqs else None) or info.get("filepath") or ""

    files = [path] if path else []
    if options.split_chapters and not options.trim and path:
        chapter_dir = Path(path).with_suffix("")
        parts = sorted(p for p in chapter_dir.glob(f"*.{options.fmt}")) if chapter_dir.is_dir() else []
        if parts:
            Path(path).unlink(missing_ok=True)  # keep only the per-chapter files
            files = [str(p) for p in parts]
            path = str(chapter_dir)
        elif log:
            log("No chapters found — kept the full file.")

    if options.normalize and options.mode == "audio":
        for i, f in enumerate(files, start=1):
            label = "Normalising volume…" if len(files) == 1 else f"Normalising volume ({i}/{len(files)})…"
            on_progress(Progress(None, label))
            normalize_audio(f, options.fmt, options.quality, cancel,
                            lambda fr, label=label: on_progress(Progress(fr, label)))
    return DownloadResult(path=path, files=files)


def playlist_folder(base: str, title: str) -> str:
    name = sanitize_filename(title, restricted=False).strip(" .") or "Playlist"
    return str(Path(base) / name)


def ytdlp_version() -> str:
    return yt_dlp.version.__version__


_RATE_RE = re.compile(r"^\d+(\.\d+)?[KMG]?$", re.I)


def valid_rate(text: str) -> bool:
    return not text or bool(_RATE_RE.match(text.strip()))
