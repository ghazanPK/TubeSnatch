"""Finish an app update. Runs from the *new* (staged) build, never from the folder being replaced:

    <staged>\\TubeSnatch.exe -m tubesnatch._swap --pid N --src <staged> --dst <app> [--relaunch]

Waits for the old TubeSnatch (pid N) to exit, mirrors the new build over the old folder, then
optionally relaunches. Keep this interface stable: older releases call the newer release's _swap.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

LOG = Path(tempfile.gettempdir()) / "tubesnatch-update.log"


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def wait_for_exit(pid: int, timeout: float = 120) -> None:
    if os.name == "nt":
        import ctypes

        synchronize = 0x00100000
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(synchronize, False, pid)
        if handle:
            k32.WaitForSingleObject(handle, int(timeout * 1000))
            k32.CloseHandle(handle)
    else:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.3)


def mirror(src: Path, dst: Path) -> None:
    """Make dst identical to src (delete extras, overwrite the rest)."""
    for root, dirs, files in os.walk(dst, topdown=False):
        rel = Path(root).relative_to(dst)
        for name in files:
            if not (src / rel / name).exists():
                (Path(root) / name).unlink()
        for name in dirs:
            if not (src / rel / name).exists():
                shutil.rmtree(Path(root) / name)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--relaunch", action="store_true")
    a = ap.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    log(f"update: waiting for pid {a.pid}; {src} -> {dst}")
    wait_for_exit(a.pid)
    time.sleep(0.5)
    ok = False
    for attempt in range(1, 8):
        try:
            mirror(src, dst)
            ok = True
            break
        except OSError as e:  # a file may still be locked for a moment (AV scan, Explorer preview…)
            log(f"attempt {attempt} failed: {e}")
            time.sleep(1.5)
    if ok:
        log("update: files replaced")
        (dst / "update-failed.txt").unlink(missing_ok=True)
    else:
        (dst / "update-failed.txt").write_text(
            f"TubeSnatch couldn't finish updating. Details: {LOG}\n"
            f"You can also download the latest release again and unzip it over this folder.\n", encoding="utf-8")
        log("update: FAILED")
    if a.relaunch:
        env = dict(os.environ, TUBESNATCH_UPDATED="1" if ok else "0")
        flags = 0x00000008 | 0x08000000 if os.name == "nt" else 0  # DETACHED_PROCESS | CREATE_NO_WINDOW
        subprocess.Popen([str(dst / "TubeSnatch.exe")], env=env, cwd=str(dst), creationflags=flags, close_fds=True)
        log("update: relaunched")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
        sys.exit(1)
