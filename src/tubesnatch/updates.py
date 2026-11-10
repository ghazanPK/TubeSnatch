"""Self-update support (Qt-free).

Two independent layers:

* **Engine update**: upgrades yt-dlp (+ the matching yt-dlp-ejs) inside the portable runtime with
  pip, using version data from the PyPI JSON API (https://pypi.org). This is the quick fix when YouTube
  changes something, and it doesn't need a new TubeSnatch release.
* **App update**: checks the project's GitHub Releases (https://docs.github.com/en/rest/releases) for a
  newer portable zip, verifies its SHA-256, and swaps the app folder after TubeSnatch exits.

Both only apply to the portable Windows build (``<app>/TubeSnatch.exe``). Running from source,
use ``uv`` instead.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable

from . import GITHUB_REPO, __version__
from .ffmpeg import NO_WINDOW

USER_AGENT = f"TubeSnatch/{__version__} (+https://github.com/{GITHUB_REPO})"
ASSET_RE = re.compile(r"-win64-portable\.zip$")


# --------------------------------------------------------------------------- versions


def parse_version(v: str) -> tuple[int, ...]:
    """'v1.2.3' → (1, 2, 3); '2026.10.26' → (2026, 10, 26); '2026.11.10.233421.dev0' → (2026, 11, 10, 233421)."""
    nums = re.findall(r"\d+", v.split("+")[0].replace(".dev", ".x"))
    out = [int(n) for n in nums]
    while out and out[-1] == 0 and len(out) > 3:
        out.pop()
    return tuple(out)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def _get_json(url: str, timeout: float = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------------------- portable layout


def app_dir() -> Path:
    """The portable app folder: <app>/TubeSnatch.exe (renamed signed pythonw.exe), python.exe, Lib/, bin/."""
    return Path(sys.executable).resolve().parent


def is_portable() -> bool:
    d = app_dir()
    return (
        os.name == "nt"
        and not getattr(sys, "frozen", False)
        and (d / "bin").is_dir()
        and (d / "TubeSnatch.exe").is_file()
        and (d / "Lib" / "site-packages" / "tubesnatch").is_dir()
    )


def is_writable(folder: Path) -> bool:
    try:
        with tempfile.TemporaryFile(dir=folder):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------- engine (yt-dlp)


@dataclass
class EngineInfo:
    installed: str
    latest: str
    ejs_pin: str | None  # exact yt-dlp-ejs version required by that yt-dlp, if any
    channel: str

    @property
    def update_available(self) -> bool:
        return is_newer(self.latest, self.installed)


def installed_version(pkg: str) -> str:
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return "0"


def check_engine(channel: str = "stable") -> EngineInfo:
    """channel: 'stable' (PyPI releases) or 'nightly' (yt-dlp's PyPI pre-releases)."""
    data = _get_json("https://pypi.org/pypi/yt-dlp/json")
    if channel == "nightly":
        candidates = [v for v, files in data.get("releases", {}).items() if files and not all(f.get("yanked") for f in files)]
        latest = max(candidates, key=parse_version)
        if parse_version(data["info"]["version"]) >= parse_version(latest):
            latest = data["info"]["version"]
    else:
        latest = data["info"]["version"]
    meta = _get_json(f"https://pypi.org/pypi/yt-dlp/{latest}/json")
    pin = None
    for req in meta["info"].get("requires_dist") or []:
        m = re.match(r"yt-dlp-ejs\s*==\s*([\w.]+)", req)
        if m:
            pin = m.group(1)
            break
    return EngineInfo(installed_version("yt-dlp"), latest, pin, channel)


def upgrade_engine(info: EngineInfo, log: Callable[[str], None] | None = None) -> str:
    """pip-install the target yt-dlp (+ matching yt-dlp-ejs) into the portable runtime. Needs a restart."""
    if not is_portable():
        raise RuntimeError("Engine updates are only available in the portable Windows build "
                           "(running from source? use `uv lock --upgrade-package yt-dlp`).")
    if not is_writable(app_dir() / "Lib" / "site-packages"):
        raise RuntimeError(f"No write access to {app_dir()} — move TubeSnatch to a folder you own.")
    python = app_dir() / "python.exe"
    pkgs = [f"yt-dlp=={info.latest}", f"yt-dlp-ejs=={info.ejs_pin}" if info.ejs_pin else "yt-dlp-ejs"]
    cmd = [str(python), "-m", "pip", "install", "--upgrade", "--no-deps", "--disable-pip-version-check",
           "--no-warn-script-location", "--no-cache-dir", *pkgs]
    if log:
        log("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
    out = (proc.stdout or "") + (proc.stderr or "")
    if log:
        log(out)
    if proc.returncode != 0:
        tail = [ln for ln in out.splitlines() if ln.strip()][-3:]
        raise RuntimeError("pip failed: " + " ".join(tail))
    return info.latest


# --------------------------------------------------------------------------- app releases


@dataclass
class ReleaseInfo:
    version: str
    tag: str
    notes: str
    html_url: str
    zip_url: str
    zip_name: str
    size: int
    sums_url: str | None


def check_app(repo: str = GITHUB_REPO) -> ReleaseInfo | None:
    """Latest GitHub release if it's newer than this build, else None."""
    data = _get_json(f"https://api.github.com/repos/{repo}/releases/latest")
    tag = data.get("tag_name") or ""
    if not tag or not is_newer(tag, __version__):
        return None
    assets = data.get("assets") or []
    zip_asset = next((a for a in assets if ASSET_RE.search(a.get("name", ""))), None)
    if not zip_asset:
        return None
    sums = next((a for a in assets if a.get("name", "").upper().startswith("SHA256SUMS")), None)
    return ReleaseInfo(
        version=tag.lstrip("v"),
        tag=tag,
        notes=data.get("body") or "",
        html_url=data.get("html_url") or f"https://github.com/{repo}/releases",
        zip_url=zip_asset["browser_download_url"],
        zip_name=zip_asset["name"],
        size=int(zip_asset.get("size") or 0),
        sums_url=sums["browser_download_url"] if sums else None,
    )


def _download(url: str, dest: Path, on_progress: Callable[[float | None], None] | None,
              cancel: threading.Event | None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, dest.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 16):
            if cancel is not None and cancel.is_set():
                raise RuntimeError("Cancelled")
            f.write(chunk)
            done += len(chunk)
            if on_progress:
                on_progress(done / total if total else None)


def download_release(info: ReleaseInfo, on_progress: Callable[[float | None], None] | None = None,
                     cancel: threading.Event | None = None) -> Path:
    """Download + verify + extract the release. Returns the staged app folder."""
    work = Path(tempfile.mkdtemp(prefix="tubesnatch-update-"))
    zpath = work / info.zip_name
    _download(info.zip_url, zpath, on_progress, cancel)
    if info.sums_url:
        sums = work / "SHA256SUMS.txt"
        _download(info.sums_url, sums, None, cancel)
        expected = None
        for line in sums.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == info.zip_name:
                expected = parts[0].lower()
        h = hashlib.sha256()
        with zpath.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if expected and h.hexdigest() != expected:
            raise RuntimeError("Downloaded update is corrupted (SHA-256 mismatch).")
    out = work / "extracted"
    with zipfile.ZipFile(zpath) as z:
        z.extractall(out)
    zpath.unlink()
    staged = next((p for p in out.iterdir() if (p / "TubeSnatch.exe").is_file() and (p / "Lib").is_dir()), None)
    if staged is None:
        raise RuntimeError("The update package doesn't look like a TubeSnatch portable build.")
    return staged


def swap_command(staged: Path, target: Path, pid: int, relaunch: bool) -> list[str]:
    """The new build's own signed TubeSnatch.exe finishes the update (see tubesnatch._swap).

    (A .cmd script doesn't work here: console tools like tasklist/find hang without a console.)
    """
    cmd = [str(staged / "TubeSnatch.exe"), "-m", "tubesnatch._swap", "--pid", str(pid),
           "--src", str(staged), "--dst", str(target)]
    if relaunch:
        cmd.append("--relaunch")
    return cmd


def apply_update(staged: Path, relaunch: bool = True) -> None:
    """Start the swap detached. The caller must quit the app right after."""
    target = app_dir()
    if not is_writable(target):
        raise RuntimeError(f"No write access to {target} — move TubeSnatch to a folder you own.")
    spawn_detached(swap_command(staged, target, os.getpid(), relaunch))


def cleanup_staging(max_age_hours: float = 1) -> None:
    """Remove old update staging folders from %TEMP% (the swap can't delete the folder it runs from)."""
    cutoff = time.time() - max_age_hours * 3600
    for d in Path(tempfile.gettempdir()).glob("tubesnatch-update-*"):
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


DETACHED_PROCESS = 0x00000008
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def spawn_detached(cmd: list[str]) -> None:
    """Start a process that outlives TubeSnatch, even if we run inside a kill-on-close job object."""
    if os.name != "nt":
        subprocess.Popen(cmd, close_fds=True, start_new_session=True, cwd=tempfile.gettempdir())
        return
    base = NO_WINDOW | DETACHED_PROCESS
    try:
        subprocess.Popen(cmd, creationflags=base | CREATE_BREAKAWAY_FROM_JOB, close_fds=True, cwd=tempfile.gettempdir())
    except OSError:  # the job doesn't allow breakaway — best effort without it
        subprocess.Popen(cmd, creationflags=base, close_fds=True, cwd=tempfile.gettempdir())


def restart_app() -> None:
    """Relaunch TubeSnatch (portable or from source). The caller quits afterwards."""
    if is_portable():
        cmd = [str(app_dir() / "TubeSnatch.exe")]
    else:
        cmd = [sys.executable, "-m", "tubesnatch"]
    spawn_detached(cmd)


# --------------------------------------------------------------------------- shortcuts


def ensure_shortcuts(desktop: bool = False, start_menu: bool = False) -> list[str]:
    """Create TubeSnatch shortcuts (with the TubeSnatch icon) on the Desktop and/or in the Start menu."""
    if not is_portable():
        return []
    app = app_dir()
    places = []
    if desktop:
        places.append("[Environment]::GetFolderPath('Desktop')")
    if start_menu:
        places.append("[Environment]::GetFolderPath('Programs')")
    if not places:
        return []
    script = (
        f"$app = '{app}'; $ws = New-Object -ComObject WScript.Shell; "
        f"foreach ($p in @({', '.join(places)})) {{ "
        "$s = $ws.CreateShortcut((Join-Path $p 'TubeSnatch.lnk')); "
        "$s.TargetPath = (Join-Path $app 'TubeSnatch.exe'); "
        "$s.WorkingDirectory = $app; $s.IconLocation = (Join-Path $app 'TubeSnatch.ico'); "
        "$s.Description = 'TubeSnatch - video and playlist downloader'; $s.Save() }"
    )
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                   creationflags=NO_WINDOW, capture_output=True, check=True)
    return places
