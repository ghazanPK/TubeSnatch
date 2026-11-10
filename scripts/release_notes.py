"""Write release notes for a tag.

    python scripts/release_notes.py vX.Y.Z dist/TubeSnatch/VERSIONS.txt > notes.md

Includes: commits since the previous tag, bundled component versions, install steps.
"""

import subprocess
import sys
from pathlib import Path


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False).stdout.strip()


def main() -> None:
    tag = sys.argv[1]
    versions = Path(sys.argv[2]).read_text(encoding="utf-8-sig").strip() if len(sys.argv) > 2 else ""
    prev = git("describe", "--tags", "--abbrev=0", f"{tag}^") if tag else ""
    rng = f"{prev}..{tag}" if prev else tag
    commits = git("log", "--no-merges", "--format=- %s", rng)

    out = [f"## TubeSnatch {tag}", ""]
    if commits:
        out += ["### Changes", commits, ""]
    if versions:
        out += ["### Bundled components", "```", versions, "```", ""]
    out += [
        "### Install / update",
        "1. Download **`TubeSnatch-*-win64-portable.zip`** below and unzip it anywhere you can write to "
        "(e.g. `C:\\Apps\\TubeSnatch` — not *Program Files*).",
        "2. Double-click **`TubeSnatch.exe`** in that folder. For Desktop / Start menu shortcuts use "
        "*Settings → Shortcuts*.",
        "3. Already using TubeSnatch? It updates itself — *Settings → Updates*.",
        "",
        "Verify the download with `SHA256SUMS.txt`. Runs with Windows 11 Smart App Control on: "
        "`TubeSnatch.exe` is the python.org-signed `pythonw.exe` (hence the Python icon in Explorer).",
        "",
        "Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org) "
        "([gyan.dev builds](https://www.gyan.dev/ffmpeg/builds/)), [Deno](https://deno.com), "
        "[SponsorBlock](https://sponsor.ajay.app) and [Qt for Python](https://doc.qt.io/qtforpython-6/). "
        "See THIRD_PARTY_NOTICES.md.",
    ]
    print("\n".join(out))


if __name__ == "__main__":
    main()
